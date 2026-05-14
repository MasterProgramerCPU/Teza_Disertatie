"""Dedicated LSTM runner.

Consumes prediction jobs from Redis list ``epimodel:jobs:lstm``, trains a
small univariate LSTM over the dataset's infected time series, writes observed,
fitted and forecast values into ``simulation_results``, and records execution
metrics in ``benchmarks``.
"""

from __future__ import annotations

import json
import os
import resource
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import psycopg
import redis
from psycopg.rows import dict_row
from psycopg.types.json import Json

QUEUE = "epimodel:jobs:lstm"
BRPOP_TIMEOUT_SEC = 5
ERROR_BACKOFF_SEC = 2
TEST_FRACTION = 0.2  # ultima parte a seriei, tinuta deoparte pentru evaluarea generalizarii

_running = True


def _handle_signal(signum, _frame):
    global _running
    print(f"signal {signum} received, shutting down", file=sys.stderr, flush=True)
    _running = False


def _peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


@dataclass
class SampleSet:
    x: np.ndarray
    y: np.ndarray


@dataclass
class TrainOutcome:
    fitted: list[float | None]  # predictii o-zi-inainte, lungime egala cu seria
    forecast: list[float]       # prognoza autoregresiva dincolo de ultima zi observata
    train_end: int              # primul indice al ferestrei de test
    mae: float
    rmse: float
    nrmse: float


class LSTMRegressor:
    def __init__(self, hidden_size: int, learning_rate: float, seed: int = 42) -> None:
        self.hidden_size = hidden_size
        self.learning_rate = learning_rate
        rng = np.random.default_rng(seed)
        width = hidden_size + 1
        scale = 0.1

        self.wf = rng.normal(0.0, scale, (hidden_size, width))
        self.wi = rng.normal(0.0, scale, (hidden_size, width))
        self.wo = rng.normal(0.0, scale, (hidden_size, width))
        self.wg = rng.normal(0.0, scale, (hidden_size, width))
        self.bf = np.full((hidden_size, 1), 0.5)
        self.bi = np.zeros((hidden_size, 1))
        self.bo = np.zeros((hidden_size, 1))
        self.bg = np.zeros((hidden_size, 1))
        self.wy = rng.normal(0.0, scale, (1, hidden_size))
        self.by = np.zeros((1, 1))

    def forward(self, seq: np.ndarray) -> tuple[float, list[dict[str, np.ndarray]]]:
        h = np.zeros((self.hidden_size, 1))
        c = np.zeros((self.hidden_size, 1))
        cache: list[dict[str, np.ndarray]] = []

        for value in seq:
            x = np.array([[float(value)]])
            h_prev = h
            c_prev = c
            z = np.vstack([h_prev, x])

            f = _sigmoid(self.wf @ z + self.bf)
            i = _sigmoid(self.wi @ z + self.bi)
            o = _sigmoid(self.wo @ z + self.bo)
            g = np.tanh(self.wg @ z + self.bg)

            c = f * c_prev + i * g
            h = o * np.tanh(c)
            cache.append({
                "z": z,
                "f": f,
                "i": i,
                "o": o,
                "g": g,
                "c": c,
                "c_prev": c_prev,
                "h": h,
            })

        y_hat = float((self.wy @ h + self.by)[0, 0])
        return y_hat, cache

    def predict(self, seq: np.ndarray) -> float:
        y_hat, _ = self.forward(seq)
        return y_hat

    def train_one(self, seq: np.ndarray, target: float) -> float:
        y_hat, cache = self.forward(seq)
        error = y_hat - float(target)

        grads = {
            "wf": np.zeros_like(self.wf),
            "wi": np.zeros_like(self.wi),
            "wo": np.zeros_like(self.wo),
            "wg": np.zeros_like(self.wg),
            "bf": np.zeros_like(self.bf),
            "bi": np.zeros_like(self.bi),
            "bo": np.zeros_like(self.bo),
            "bg": np.zeros_like(self.bg),
            "wy": np.zeros_like(self.wy),
            "by": np.zeros_like(self.by),
        }

        dy = 2.0 * error
        grads["wy"] += dy * cache[-1]["h"].T
        grads["by"] += dy

        dh_next = self.wy.T * dy
        dc_next = np.zeros((self.hidden_size, 1))

        for step in reversed(cache):
            z = step["z"]
            f = step["f"]
            i = step["i"]
            o = step["o"]
            g = step["g"]
            c = step["c"]
            c_prev = step["c_prev"]

            tanh_c = np.tanh(c)
            do = dh_next * tanh_c
            dao = do * o * (1.0 - o)

            dc = dh_next * o * (1.0 - tanh_c * tanh_c) + dc_next
            df = dc * c_prev
            daf = df * f * (1.0 - f)
            di = dc * g
            dai = di * i * (1.0 - i)
            dg = dc * i
            dag = dg * (1.0 - g * g)

            grads["wf"] += daf @ z.T
            grads["wi"] += dai @ z.T
            grads["wo"] += dao @ z.T
            grads["wg"] += dag @ z.T
            grads["bf"] += daf
            grads["bi"] += dai
            grads["bo"] += dao
            grads["bg"] += dag

            dz = self.wf.T @ daf + self.wi.T @ dai + self.wo.T @ dao + self.wg.T @ dag
            dh_next = dz[: self.hidden_size]
            dc_next = dc * f

        for key, grad in grads.items():
            np.clip(grad, -5.0, 5.0, out=grad)
            setattr(self, key, getattr(self, key) - self.learning_rate * grad)

        return float(error * error)


def fetch_infected_series(conn: psycopg.Connection, dataset_id: str) -> np.ndarray:
    rows = conn.execute(
        """
        SELECT infected
        FROM epidemiological_records
        WHERE dataset_id = %s
        ORDER BY recorded_date ASC, id ASC
        """,
        (dataset_id,),
    ).fetchall()
    if not rows:
        raise RuntimeError("dataset has no epidemiological records")
    return np.array([float(row["infected"]) for row in rows], dtype=float)


def make_samples(values: np.ndarray, lookback: int) -> SampleSet:
    x_rows = []
    y_rows = []
    for idx in range(lookback, len(values)):
        x_rows.append(values[idx - lookback:idx])
        y_rows.append(values[idx])
    if not x_rows:
        raise RuntimeError("not enough data points for LSTM lookback")
    return SampleSet(x=np.array(x_rows, dtype=float), y=np.array(y_rows, dtype=float))


def fit_scaler(values: np.ndarray) -> tuple[float, float]:
    """Media si abaterea standard ale normalizarii, calibrate doar pe antrenare."""
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std < 1e-9:
        std = 1.0
    return mean, std


def denormalize(value: float, mean: float, std: float) -> float:
    return max(0.0, float(value * std + mean))


def split_index(n: int, lookback: int) -> int:
    """Primul indice al ferestrei de test, dupa o impartire cronologica.

    Fereastra de test este ultima parte a seriei (``TEST_FRACTION``), dar
    portiunea de antrenare trebuie sa pastreze cel putin un esantion complet
    de lungime ``lookback``.
    """
    test_size = min(round(TEST_FRACTION * n), n - lookback - 1)
    if test_size < 1:
        raise RuntimeError("dataset prea scurt pentru o impartire train/test")
    return n - test_size


def evaluate(
    series: np.ndarray, fitted: list[float | None], train_end: int, population: float
) -> tuple[float, float, float]:
    """MAE, RMSE si nRMSE pe fereastra de test (definitii din capitolul 7)."""
    errors: list[float] = []
    for idx in range(train_end, len(series)):
        pred = fitted[idx]
        if pred is not None:
            errors.append(pred - float(series[idx]))
    if not errors:
        return 0.0, 0.0, 0.0
    arr = np.array(errors, dtype=float)
    mae = float(np.mean(np.abs(arr)))
    rmse = float(np.sqrt(np.mean(arr**2)))
    nrmse = rmse / population if population > 0 else 0.0
    return mae, rmse, nrmse


def train_model(series: np.ndarray, params: dict[str, float], population: float) -> TrainOutcome:
    lookback = int(params["lookback"])
    hidden_size = int(params["hidden_size"])
    epochs = int(params["epochs"])
    learning_rate = float(params["learning_rate"])
    horizon = int(params["forecast_horizon"])

    n = len(series)
    train_end = split_index(n, lookback)

    # Normalizarea se calibreaza exclusiv pe portiunea de antrenare, pentru a nu
    # permite scurgeri de informatie din fereastra de test.
    mean, std = fit_scaler(series[:train_end])
    normalized = (series - mean) / std

    samples = make_samples(normalized[:train_end], lookback)
    model = LSTMRegressor(hidden_size=hidden_size, learning_rate=learning_rate)
    rng = np.random.default_rng(123)
    for _ in range(epochs):
        for idx in rng.permutation(len(samples.x)):
            model.train_one(samples.x[idx], float(samples.y[idx]))

    # Predictii o-zi-inainte pe toata seria: in portiunea de antrenare sunt
    # in-sample, iar pe fereastra de test sunt out-of-sample, deoarece modelul
    # nu a vazut acele tinte.
    fitted: list[float | None] = [None] * n
    for idx in range(lookback, n):
        pred_norm = model.predict(normalized[idx - lookback:idx])
        fitted[idx] = denormalize(pred_norm, mean, std)

    mae, rmse, nrmse = evaluate(series, fitted, train_end, population)

    # Prognoza autoregresiva dincolo de ultima zi observata.
    window = list(normalized[-lookback:])
    forecast: list[float] = []
    for _ in range(horizon):
        pred_norm = model.predict(np.array(window, dtype=float))
        forecast.append(denormalize(pred_norm, mean, std))
        window = [*window[1:], pred_norm]

    return TrainOutcome(
        fitted=fitted, forecast=forecast, train_end=train_end,
        mae=mae, rmse=rmse, nrmse=nrmse,
    )


def run_lstm(conn: psycopg.Connection, job: dict[str, Any]) -> None:
    sim_id = job["simulation_id"]
    dataset_id = job["dataset_id"]
    params = {str(k): float(v) for k, v in job["parameters"].items()}
    params["forecast_horizon"] = float(int(job["t_max"]))
    population = float(job["population_n"])

    with conn.transaction():
        conn.execute(
            "UPDATE simulation_runs SET status = 'running' WHERE id = %s",
            (sim_id,),
        )

    rss_before = _peak_rss_mb()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()

    series = fetch_infected_series(conn, dataset_id)
    if len(series) <= int(params["lookback"]) + 1:
        raise RuntimeError("dataset length must exceed lookback + 1 for a train/test split")
    outcome = train_model(series, params, population)

    wall_ms = int((time.perf_counter() - wall_start) * 1000)
    cpu_ms = int((time.process_time() - cpu_start) * 1000)
    peak_mb = max(_peak_rss_mb(), rss_before)

    rows = []
    for idx, observed in enumerate(series):
        values = {"observed": max(0.0, float(observed))}
        fit = outcome.fitted[idx]
        if fit is not None:
            values["fitted"] = float(fit)
        rows.append((sim_id, idx, Json(values)))

    for step, predicted in enumerate(outcome.forecast):
        rows.append((sim_id, len(series) + step, Json({"predicted": float(predicted)})))

    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO simulation_results (simulation_id, t, compartments) VALUES (%s, %s, %s)",
                rows,
            )
            cur.execute(
                "INSERT INTO benchmarks (simulation_id, wall_time_ms, cpu_time_ms, peak_memory_mb) VALUES (%s, %s, %s, %s)",
                (sim_id, wall_ms, cpu_ms, peak_mb),
            )
            cur.execute(
                "UPDATE simulation_runs SET status = 'completed', completed_at = NOW() WHERE id = %s",
                (sim_id,),
            )

    print(
        f"lstm sim {sim_id} done: wall={wall_ms}ms cpu={cpu_ms}ms mem={peak_mb:.1f}MB "
        f"rows={len(rows)} train_end={outcome.train_end}/{len(series)} "
        f"MAE={outcome.mae:.2f} RMSE={outcome.rmse:.2f} nRMSE={outcome.nrmse:.3e}",
        flush=True,
    )


def mark_failed(conn: psycopg.Connection, sim_id: str, msg: str) -> None:
    try:
        with conn.transaction():
            conn.execute(
                "UPDATE simulation_runs SET status = 'failed', error_message = %s, completed_at = NOW() WHERE id = %s",
                (msg[:2000], sim_id),
            )
    except Exception as exc:  # noqa: BLE001
        print(f"could not mark failed: {exc}", file=sys.stderr, flush=True)


def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    redis_url = os.environ["REDIS_URL"]
    db_dsn = os.environ.get("DATABASE_URL")

    rdb = redis.from_url(redis_url)
    rdb.ping()
    print(f"runner-lstm connected to redis, consuming {QUEUE}", flush=True)

    while _running:
        try:
            item = rdb.brpop(QUEUE, timeout=BRPOP_TIMEOUT_SEC)
        except redis.RedisError as exc:
            print(f"redis error: {exc}", file=sys.stderr, flush=True)
            time.sleep(ERROR_BACKOFF_SEC)
            continue
        if item is None:
            continue

        _, raw = item
        try:
            job = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"invalid job json: {exc}", file=sys.stderr, flush=True)
            continue

        sim_id = job.get("simulation_id", "?")
        dsn = job.get("db_dsn") or db_dsn
        if not dsn:
            print(f"sim {sim_id}: no db_dsn", file=sys.stderr, flush=True)
            continue

        try:
            if job.get("model_type") != "lstm":
                raise RuntimeError(f"runner-lstm received unsupported model_type: {job.get('model_type')}")
            with psycopg.connect(dsn, row_factory=dict_row) as conn:
                run_lstm(conn, job)
        except Exception as exc:  # noqa: BLE001
            print(f"sim {sim_id} failed: {exc}", file=sys.stderr, flush=True)
            try:
                with psycopg.connect(dsn) as conn:
                    mark_failed(conn, sim_id, str(exc))
            except Exception as inner:  # noqa: BLE001
                print(f"could not connect to mark failed: {inner}", file=sys.stderr, flush=True)

    print("runner-lstm stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
