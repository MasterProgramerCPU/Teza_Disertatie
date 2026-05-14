"""Epidemiological model runner — Python.

Consumes simulation jobs from Redis list ``epimodel:jobs:python`` (BRPOP),
solves SIS/SIR/SEIR/SIRS/SIDARTHE ODE systems with
``scipy.integrate.solve_ivp`` (RK45),
inserts compartment trajectories into YugabyteDB and records the benchmark
(wall time, CPU time, peak RSS) into ``benchmarks``.
"""

from __future__ import annotations

import json
import os
import resource
import signal
import sys
import time
from typing import Any

import numpy as np
import psycopg
import redis
from psycopg.rows import dict_row
from psycopg.types.json import Json
from scipy.integrate import solve_ivp

QUEUE = "epimodel:jobs:python"
BRPOP_TIMEOUT_SEC = 5
ERROR_BACKOFF_SEC = 2

_running = True


def _handle_signal(signum, _frame):
    global _running
    print(f"signal {signum} received, shutting down", file=sys.stderr, flush=True)
    _running = False


def sir_rhs(t: float, y: np.ndarray, params: dict[str, float], n: float) -> list[float]:
    del t
    s, i, r = y
    beta = params["beta"]
    gamma = params["gamma"]
    return [
        -beta * s * i / n,
        beta * s * i / n - gamma * i,
        gamma * i,
    ]


def sis_rhs(t: float, y: np.ndarray, params: dict[str, float], n: float) -> list[float]:
    del t
    s, i = y
    beta = params["beta"]
    gamma = params["gamma"]
    infections = beta * s * i / n
    recoveries = gamma * i
    return [-infections + recoveries, infections - recoveries]


def seir_rhs(t: float, y: np.ndarray, params: dict[str, float], n: float) -> list[float]:
    del t
    s, e, i, r = y
    beta = params["beta"]
    sigma = params["sigma"]
    gamma = params["gamma"]
    infections = beta * s * i / n
    return [
        -infections,
        infections - sigma * e,
        sigma * e - gamma * i,
        gamma * i,
    ]


def sirs_rhs(t: float, y: np.ndarray, params: dict[str, float], n: float) -> list[float]:
    del t
    s, i, r = y
    beta = params["beta"]
    gamma = params["gamma"]
    xi = params["xi"]
    infections = beta * s * i / n
    recoveries = gamma * i
    waning = xi * r
    return [-infections + waning, infections - recoveries, recoveries - waning]


def sidarthe_rhs(t: float, y: np.ndarray, params: dict[str, float], n: float) -> list[float]:
    del t
    s, i, d, a, r, threatened, h, extinct = y
    del extinct
    force = (params["alpha"] * i + params["beta"] * d + params["gamma"] * a + params["delta"] * r) / n
    new_infections = s * force

    return [
        -new_infections,
        new_infections - (params["epsilon"] + params["zeta"] + params["lambda"]) * i,
        params["epsilon"] * i - (params["eta"] + params["rho"]) * d,
        params["zeta"] * i - (params["theta"] + params["mu"] + params["kappa"]) * a,
        params["eta"] * d + params["theta"] * a - (params["nu"] + params["xi"]) * r,
        params["mu"] * a + params["nu"] * r - (params["sigma"] + params["tau"]) * threatened,
        params["lambda"] * i + params["rho"] * d + params["kappa"] * a + params["xi"] * r + params["sigma"] * threatened,
        params["tau"] * threatened,
    ]


def model_layout(model_type: str) -> tuple[list[str], Any]:
    if model_type == "sis":
        return ["s", "i"], sis_rhs
    if model_type == "sir":
        return ["s", "i", "r"], sir_rhs
    if model_type == "seir":
        return ["s", "e", "i", "r"], seir_rhs
    if model_type == "sirs":
        return ["s", "i", "r"], sirs_rhs
    if model_type == "sidarthe":
        return ["s", "i", "d", "a", "r", "t", "h", "e"], sidarthe_rhs
    raise ValueError(f"unsupported model_type: {model_type}")


def _peak_rss_mb() -> float:
    """Return peak RSS in MB across platforms.

    Linux returns ``ru_maxrss`` in KiB, macOS in bytes.
    """
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024 * 1024)
    return rss / 1024


def run_simulation(conn: psycopg.Connection, job: dict[str, Any]) -> None:
    sim_id = job["simulation_id"]
    model_type = job.get("model_type", "sidarthe")
    params = {str(k): float(v) for k, v in job["parameters"].items()}
    initial = {str(k): float(v) for k, v in job["initial"].items()}
    n = float(job["population_n"])
    t_max = int(job["t_max"])
    compartments, rhs = model_layout(model_type)
    y0 = [initial.get(name, 0.0) for name in compartments]

    with conn.transaction():
        conn.execute(
            "UPDATE simulation_runs SET status = 'running' WHERE id = %s",
            (sim_id,),
        )

    rss_before = _peak_rss_mb()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()

    sol = solve_ivp(
        fun=rhs,
        t_span=(0.0, float(t_max)),
        y0=y0,
        method="RK45",
        t_eval=np.arange(0, t_max + 1, dtype=float),
        args=(params, n),
        rtol=1e-8,
        atol=1e-10,
    )
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed: {sol.message}")

    wall_ms = int((time.perf_counter() - wall_start) * 1000)
    cpu_ms = int((time.process_time() - cpu_start) * 1000)
    peak_mb = max(_peak_rss_mb(), rss_before)

    rows = []
    for idx, t in enumerate(sol.t):
        values = {
            name: max(0.0, float(sol.y[pos][idx]))
            for pos, name in enumerate(compartments)
        }
        rows.append((sim_id, int(t), Json(values)))

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
        f"sim {sim_id} done: wall={wall_ms}ms cpu={cpu_ms}ms mem={peak_mb:.1f}MB rows={len(rows)}",
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
    print(f"runner-python connected to redis, consuming {QUEUE}", flush=True)

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
            with psycopg.connect(dsn, row_factory=dict_row) as conn:
                run_simulation(conn, job)
        except Exception as exc:  # noqa: BLE001
            print(f"sim {sim_id} failed: {exc}", file=sys.stderr, flush=True)
            try:
                with psycopg.connect(dsn) as conn:
                    mark_failed(conn, sim_id, str(exc))
            except Exception as inner:  # noqa: BLE001
                print(f"could not connect to mark failed: {inner}", file=sys.stderr, flush=True)

    print("runner-python stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
