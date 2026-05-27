"""Wrapper pentru runner-ele plug-in definite de utilizator.

Acelasi container ruleaza pentru fiecare runner inregistrat in tabela `runners`;
ce diferentiaza pod-urile este variabila de mediu ``RUNNER_ID``, care identifica
unic inregistrarea din DB. La pornire, wrapper-ul:

  1. citeste manifestul (nume, script, parameter_schema, queue_name) din DB;
  2. marcheaza runner-ul ca ``ready``;
  3. compileaza scriptul user-ului ca modul Python;
  4. asculta pe coada Redis declarata si proceseaza job-uri.

Pentru fiecare job (un mesaj similar cu cele consumate de runner-ele built-in):

  * fetch din ``epidemiological_records`` pe baza ``dataset_id``;
  * apel ``user_module.main(records, parameters, context)``, cu timeout si
    masuratori wall-time / CPU / memorie de varf;
  * validare output (lista de ``{"t": int, "compartments": {key: float}}``);
  * scriere bulk in ``simulation_results`` + ``benchmarks``;
  * marcare ``simulation_runs.status = completed`` (sau ``failed`` la exceptie).

Contractul scriptului user este intentionat minimalist:

    def main(records: list[dict], parameters: dict, context: dict) -> list[dict]:
        ...
        return [{"t": 0, "compartments": {"observed": 1.23, ...}}, ...]

Aceasta arhitectura permite executarea oricarui algoritm Python --- nu doar
modele compartimentale --- intr-un mediu standard, fara modificari ale API-ului
sau a runner-elor existente.
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

RUNNER_ID = os.environ["RUNNER_ID"]
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


def load_manifest(conn) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, script_content, parameter_schema, queue_name "
            "FROM runners WHERE id = %s",
            (RUNNER_ID,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"runner {RUNNER_ID} not found in DB")
        name, script, schema, queue = row
        return {"name": name, "script_content": script,
                "parameter_schema": schema, "queue_name": queue}


def mark_ready(conn: psycopg.Connection) -> None:
    with conn.transaction():
        conn.execute(
            "UPDATE runners SET status = 'ready', status_message = '', "
            "ready_at = COALESCE(ready_at, NOW()) WHERE id = %s",
            (RUNNER_ID,),
        )


def load_user_module(script_content: str):
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
        # convert all values to float; reject non-numeric
        clean = {str(k): float(v) for k, v in comp.items()}
        out.append({"t": t, "compartments": clean})
    return out


def run_job(conn: psycopg.Connection, user_module, job: dict) -> None:
    sim_id = job["simulation_id"]
    dataset_id = job["dataset_id"]
    parameters = job.get("parameters", {})
    context = {
        "population_n": job.get("population_n"),
        "t_max": job.get("t_max"),
        "runner_id": RUNNER_ID,
    }

    with conn.transaction():
        conn.execute(
            "UPDATE simulation_runs SET status = 'running' WHERE id = %s",
            (sim_id,),
        )

    records = fetch_records(conn, dataset_id)

    wall0 = time.perf_counter()
    cpu0 = time.process_time()
    rusage_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    raw_results = user_module.main(records, parameters, context)
    wall_ms = int(round((time.perf_counter() - wall0) * 1000))
    cpu_ms = int(round((time.process_time() - cpu0) * 1000))
    peak_kb = max(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        rusage_before,
    )
    # ru_maxrss e in KB pe Linux, in B pe macOS; presupunem Linux (container).
    peak_mb = peak_kb / 1024.0

    results = validate_results(raw_results)

    rows = [(sim_id, r["t"], Json(r["compartments"])) for r in results]
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO simulation_results (simulation_id, t, compartments) VALUES (%s, %s, %s)",
                rows,
            )
            cur.execute(
                "INSERT INTO benchmarks (simulation_id, wall_time_ms, cpu_time_ms, peak_memory_mb) "
                "VALUES (%s, %s, %s, %s)",
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
                "UPDATE simulation_runs SET status = 'failed', "
                "error_message = %s, completed_at = NOW() WHERE id = %s",
                (msg[:2000], sim_id),
            )
    except Exception as exc:
        print(f"could not mark failed: {exc}", file=sys.stderr, flush=True)


def main() -> int:
    signal.signal(signal.SIGINT, _signal)
    signal.signal(signal.SIGTERM, _signal)

    # 1. Load manifest + script
    with psycopg.connect(DB_URL) as conn:
        manifest = load_manifest(conn)
        name = manifest["name"]
        queue_name = manifest["queue_name"]
        script_content = manifest["script_content"]
        try:
            user_module = load_user_module(script_content)
        except Exception as exc:
            with conn.transaction():
                conn.execute(
                    "UPDATE runners SET status = 'failed', status_message = %s WHERE id = %s",
                    (str(exc)[:500], RUNNER_ID),
                )
            print(f"FATAL: cannot load user script: {exc}", file=sys.stderr, flush=True)
            return 1
        mark_ready(conn)
    print(f"runner-custom[{name}] ready, listening on {queue_name}", flush=True)

    # 2. Consume Redis queue
    rdb = redis.from_url(REDIS_URL)
    rdb.ping()

    while _running:
        try:
            item = rdb.brpop(queue_name, timeout=BRPOP_TIMEOUT_SEC)
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
                run_job(conn, user_module, job)
        except Exception as exc:
            print(f"sim {sim_id} failed: {exc}", file=sys.stderr, flush=True)
            try:
                with psycopg.connect(DB_URL) as conn:
                    mark_failed(conn, sim_id, str(exc))
            except Exception as inner:
                print(f"could not mark failed: {inner}", file=sys.stderr, flush=True)

    print(f"runner-custom[{name}] stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
