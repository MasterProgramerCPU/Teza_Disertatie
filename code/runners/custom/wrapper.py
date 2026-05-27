"""Executor partajat pentru simularile de tip 'script'.

Acelasi container ruleaza ca Deployment K8s permanent (runner-script). Pentru
fiecare job consumat din coada Redis, primeste in mesaj campul script_content
(scris de cercetator in editorul UI), il compileaza ad-hoc ca modul Python,
ii apeleaza functia main() si scrie rezultatele in baza de date.

Contractul scriptului user este:

    def main(records: list[dict],
             parameters: dict,
             context: dict) -> list[dict]:
        # records: rândurile dataset-ului (date, region, infected, ...)
        # parameters: dict cu parametri (validati de API)
        # context: {population_n, t_max, simulation_id, ...}
        return [{"t": int, "compartments": {nume: float, ...}}, ...]

Spre deosebire de runner-ele built-in (R/Julia/Python compartimentale, LSTM),
acest wrapper nu cunoaste apriori structura modelelor: doar primeste script,
ruleaza si valideaza formatul rezultatului inainte sa-l persiste.

Variabile de mediu:
    RUNNER_QUEUE   coada Redis de ascultat (default: epimodel:jobs:script)
    DATABASE_URL   conexiunea YugabyteDB
    REDIS_URL      conexiunea Redis
"""

from __future__ import annotations

import importlib.util
import json
import os
import resource
import signal
import sys
import time
from typing import Any

import psycopg
import redis
from psycopg.types.json import Json

QUEUE = os.environ.get("RUNNER_QUEUE", "epimodel:jobs:script")
DB_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
BRPOP_TIMEOUT_SEC = 5
ERROR_BACKOFF_SEC = 2
SCRIPT_PATH = "/tmp/entry.py"

_running = True


def _signal(signum, _frame):
    global _running
    print(f"signal {signum}, shutting down", file=sys.stderr, flush=True)
    _running = False


def load_user_module(script_content: str):
    """Scrie scriptul intr-un fisier temporar si il incarca ca modul Python.

    Importam la fiecare job pentru a nu lasa stare globala intre executii.
    """
    with open(SCRIPT_PATH, "w") as f:
        f.write(script_content)
    spec = importlib.util.spec_from_file_location("user_entry", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load user script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "main"):
        raise RuntimeError("user script must define main(records, parameters, context)")
    return module


def fetch_records(conn, dataset_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT recorded_date, region_code, susceptible, infected, recovered, population "
            "FROM epidemiological_records WHERE dataset_id = %s ORDER BY recorded_date",
            (dataset_id,),
        )
        rows = cur.fetchall()
    out = []
    for date, region, susceptible, infected, recovered, population in rows:
        out.append({
            "date": date.isoformat() if date else None,
            "region": region,
            "susceptible": int(susceptible) if susceptible is not None else None,
            "infected": int(infected),
            "recovered": int(recovered) if recovered is not None else None,
            "population": int(population),
        })
    return out


def validate_results(results: Any) -> list[dict]:
    if not isinstance(results, list):
        raise RuntimeError("main() must return a list, got " + type(results).__name__)
    out: list[dict] = []
    for i, item in enumerate(results):
        if not isinstance(item, dict) or "t" not in item or "compartments" not in item:
            raise RuntimeError(f"results[{i}] must be {{'t': int, 'compartments': dict}}")
        t = int(item["t"])
        comp = item["compartments"]
        if not isinstance(comp, dict):
            raise RuntimeError(f"results[{i}].compartments must be dict")
        clean = {str(k): float(v) for k, v in comp.items()}
        out.append({"t": t, "compartments": clean})
    return out


def run_job(conn, job: dict) -> None:
    sim_id = job["simulation_id"]
    dataset_id = job["dataset_id"]
    script_content = job.get("script_content", "")
    if not script_content:
        raise RuntimeError("job missing script_content")

    parameters = job.get("parameters", {}) or {}
    context = {
        "simulation_id": sim_id,
        "population_n": job.get("population_n"),
        "t_max": job.get("t_max"),
    }

    user_module = load_user_module(script_content)

    with conn.transaction():
        conn.execute(
            "UPDATE simulation_runs SET status = 'running' WHERE id = %s",
            (sim_id,),
        )

    records = fetch_records(conn, dataset_id)

    wall0 = time.perf_counter()
    cpu0 = time.process_time()
    raw_results = user_module.main(records, parameters, context)
    wall_ms = int(round((time.perf_counter() - wall0) * 1000))
    cpu_ms = int(round((time.process_time() - cpu0) * 1000))
    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = peak_kb / 1024.0  # Linux: ru_maxrss e in KB.

    results = validate_results(raw_results)

    rows = [(sim_id, r["t"], Json(r["compartments"])) for r in results]
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO simulation_results (simulation_id, t, compartments) "
                "VALUES (%s, %s, %s)",
                rows,
            )
            cur.execute(
                "INSERT INTO benchmarks (simulation_id, wall_time_ms, cpu_time_ms, peak_memory_mb) "
                "VALUES (%s, %s, %s, %s)",
                (sim_id, wall_ms, cpu_ms, peak_mb),
            )
            cur.execute(
                "UPDATE simulation_runs SET status = 'completed', completed_at = NOW() "
                "WHERE id = %s",
                (sim_id,),
            )
    print(
        f"sim {sim_id} done: wall={wall_ms}ms cpu={cpu_ms}ms mem={peak_mb:.1f}MB rows={len(rows)}",
        flush=True,
    )


def mark_failed(conn, sim_id: str, msg: str) -> None:
    try:
        with conn.transaction():
            conn.execute(
                "UPDATE simulation_runs SET status = 'failed', "
                "error_message = %s, completed_at = NOW() WHERE id = %s",
                (msg[:2000], sim_id),
            )
    except Exception as exc:
        print(f"could not mark failed: {exc}", file=sys.stderr, flush=True)


def main() -> int:
    signal.signal(signal.SIGINT, _signal)
    signal.signal(signal.SIGTERM, _signal)

    rdb = redis.from_url(REDIS_URL)
    rdb.ping()
    print(f"runner-script ready, listening on {QUEUE}", flush=True)

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
        try:
            with psycopg.connect(DB_URL) as conn:
                run_job(conn, job)
        except Exception as exc:
            print(f"sim {sim_id} failed: {exc}", file=sys.stderr, flush=True)
            try:
                with psycopg.connect(DB_URL) as conn:
                    mark_failed(conn, sim_id, str(exc))
            except Exception as inner:
                print(f"could not mark failed: {inner}", file=sys.stderr, flush=True)

    print("runner-script stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
