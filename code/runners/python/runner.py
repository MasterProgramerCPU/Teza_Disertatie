"""SIR runner — Python.

Consumes simulation jobs from Redis list ``sir:jobs:python`` (BRPOP),
solves the SIR ODE with ``scipy.integrate.solve_ivp`` (RK45), bulk-inserts
results into YugabyteDB (table ``simulation_results``) and records the
benchmark (wall time, CPU time, peak RSS) into ``benchmarks``.
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
from scipy.integrate import solve_ivp

QUEUE = "sir:jobs:python"
LANGUAGE = "python"
BRPOP_TIMEOUT_SEC = 5
ERROR_BACKOFF_SEC = 2

_running = True


def _handle_signal(signum, _frame):
    global _running
    print(f"signal {signum} received, shutting down", file=sys.stderr, flush=True)
    _running = False


def sir_rhs(t: float, y: np.ndarray, beta: float, gamma: float, n: float) -> list[float]:
    s, i, r = y
    return [
        -beta * s * i / n,
        beta * s * i / n - gamma * i,
        gamma * i,
    ]


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
    beta = float(job["beta"])
    gamma = float(job["gamma"])
    n = float(job["population_n"])
    t_max = int(job["t_max"])
    y0 = [float(job["s0"]), float(job["i0"]), float(job["r0"])]

    with conn.transaction():
        conn.execute(
            "UPDATE simulation_runs SET status = 'running' WHERE id = %s",
            (sim_id,),
        )

    rss_before = _peak_rss_mb()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()

    sol = solve_ivp(
        fun=sir_rhs,
        t_span=(0.0, float(t_max)),
        y0=y0,
        method="RK45",
        t_eval=np.arange(0, t_max + 1, dtype=float),
        args=(beta, gamma, n),
        rtol=1e-8,
        atol=1e-10,
    )
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed: {sol.message}")

    wall_ms = int((time.perf_counter() - wall_start) * 1000)
    cpu_ms = int((time.process_time() - cpu_start) * 1000)
    peak_mb = max(_peak_rss_mb(), rss_before)

    rows = [
        (sim_id, int(t), float(sol.y[0][i]), float(sol.y[1][i]), float(sol.y[2][i]))
        for i, t in enumerate(sol.t)
    ]

    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO simulation_results (simulation_id, t, s, i, r) VALUES (%s, %s, %s, %s, %s)",
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
