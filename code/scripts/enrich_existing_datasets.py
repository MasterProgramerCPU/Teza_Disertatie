"""Adauga coloanele extinse la dataseturile existente (non-distructiv).

Citeste CSV-urile procesate din ``data/processed/`` (care contin acum
coloanele extinse: deaths, new_cases, new_deaths, hospitalized, icu,
vaccinated, tested, stringency_index, reproduction_rate) si face UPDATE
in-place pe epidemiological_records, matchind pe (dataset_name, recorded_date,
region_code).

Avantaj fata de re-crearea seturilor: pastreaza intacte simulation_runs si
benchmarks-urile asociate (FK CASCADE ar fi sters totul).

Strategie eficienta: pentru fiecare CSV
  1. creeaza o tabela temporara cu valorile noi,
  2. UPDATE epidemiological_records FROM temp WHERE chei-de-match,
  3. drop temp.

Mapare nume CSV -> nume dataset in DB:
  romania.csv -> "Romania" (COVID-19 Global / Europa)
  mpox_<slug>.csv -> "<Tara>"  (Mpox Global 2022-2024)
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "code" / "data" / "processed"

# Coloane care vor fi update-uite (corespondenta CSV -> SQL).
INT_COLS = ["deaths", "new_cases", "new_deaths", "hospitalized", "icu",
            "vaccinated", "tested"]
FLOAT_COLS = ["stringency_index", "reproduction_rate"]
EXT_COLS = INT_COLS + FLOAT_COLS

logger = logging.getLogger("enrich")


def csv_dataset_info(csv_path: Path) -> tuple[str, str]:
    """Reverseaza convertirea slug -> (nume, disease_code) din preprocess_*.

    Pentru CSV ``romania.csv`` returneaza ("Romania", "covid19");
    pentru ``mpox_united_states.csv`` returneaza ("United States", "mpox").
    """
    stem = csv_path.stem
    if stem.startswith("mpox_"):
        stem = stem[len("mpox_"):]
        disease = "mpox"
    else:
        disease = "covid19"
    name = " ".join(p.capitalize() for p in stem.split("_"))
    return name, disease


def find_dataset_ids(conn, dataset_name: str, disease_code: str) -> list[str]:
    """Intoarce TOATE dataset_id-urile cu (name, disease_code) date.

    Acelasi nume de tara poate aparea in mai multe studii (COVID Global +
    COVID Europa + studiu pilot) — toate trebuie actualizate.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM datasets WHERE name = %s AND disease_code = %s",
            (dataset_name, disease_code))
        return [str(r[0]) for r in cur.fetchall()]


def enrich_one(conn, csv_path: Path) -> int:
    """Aplica UPDATE pe toate dataseturile (name, disease_code) corespunzatoare.

    Returneaza suma randurilor actualizate (pot fi mai multe dataseturi cu
    acelasi nume in studii diferite).
    """
    dataset_name, disease_code = csv_dataset_info(csv_path)
    dataset_ids = find_dataset_ids(conn, dataset_name, disease_code)
    if not dataset_ids:
        logger.warning("[%s] (%s/%s) nu exista in DB; sar peste",
                       csv_path.name, disease_code, dataset_name)
        return 0

    with open(csv_path) as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or not any(c in reader.fieldnames for c in EXT_COLS):
            logger.warning("[%s] CSV nu contine coloane extinse; sar peste",
                           csv_path.name)
            return 0

        # Citim datele o singura data si le aplicam pentru fiecare dataset_id.
        base_rows = []
        for r in reader:
            date_val = r["date"]
            region_val = r["region"]
            ext = []
            for col in INT_COLS:
                v = r.get(col, "")
                ext.append(int(float(v)) if v not in ("", None) else None)
            for col in FLOAT_COLS:
                v = r.get(col, "")
                ext.append(float(v) if v not in ("", None) else None)
            base_rows.append((date_val, region_val, ext))

    if not base_rows:
        return 0

    # Pentru fiecare dataset_id matching, construim staging row-urile cu acel ID.
    total = 0
    for dataset_id in dataset_ids:
        rows = [(dataset_id, d, r, *ext) for d, r, ext in base_rows]
        total += _update_one_dataset(conn, dataset_id, rows)
    return total


STAGING_TABLE = "enrich_staging"


def ensure_staging(conn) -> None:
    """Creeaza tabela de staging persistenta (o singura data per rulare).

    YugabyteDB se descurca prost cu CREATE/DROP repetitiv in loop (DDL e
    expensive si poate sa blocheze). Folosim o singura tabela non-temp,
    truncated intre iteratii.
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {STAGING_TABLE} (
              dataset_id UUID, recorded_date DATE, region_code TEXT,
              {", ".join(f"{c} BIGINT" for c in INT_COLS)},
              {", ".join(f"{c} REAL" for c in FLOAT_COLS)}
            )
        """)
    conn.commit()


def cleanup_staging(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE}")
    conn.commit()


def _update_one_dataset(conn, dataset_id: str, rows: list[tuple]) -> int:
    """Foloseste staging-ul persistent: TRUNCATE + COPY + UPDATE FROM."""
    set_clause = ", ".join(f"{c} = COALESCE(t.{c}, e.{c})" for c in EXT_COLS)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {STAGING_TABLE}")
        with cur.copy(
            f"COPY {STAGING_TABLE} (dataset_id, recorded_date, region_code, "
            + ", ".join(EXT_COLS) + ") FROM STDIN"
        ) as cp:
            for r in rows:
                cp.write_row(r)
        cur.execute(f"""
            UPDATE epidemiological_records e
               SET {set_clause}
              FROM {STAGING_TABLE} t
             WHERE e.dataset_id    = t.dataset_id
               AND e.recorded_date = t.recorded_date
               AND e.region_code   = t.region_code
        """)
        updated = cur.rowcount
    conn.commit()
    return updated


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dsn", default=os.environ.get(
        "DATABASE_URL",
        "postgres://yugabyte:yugabyte@127.0.0.1:15433/yugabyte?sslmode=disable"))
    p.add_argument("--pattern", default="*.csv",
                   help="glob in data/processed/ (implicit toate)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    files = sorted(PROCESSED_DIR.glob(args.pattern))
    if not files:
        logger.error("Niciun CSV gasit in %s", PROCESSED_DIR)
        return 1

    total_updated = 0
    with psycopg.connect(args.dsn) as conn:
        ensure_staging(conn)
        try:
            for csv_path in files:
                try:
                    n = enrich_one(conn, csv_path)
                    if n:
                        logger.info("[%s] %d randuri actualizate", csv_path.name, n)
                        total_updated += n
                except Exception as exc:
                    logger.error("[%s] eroare: %s", csv_path.name, exc)
        finally:
            cleanup_staging(conn)

    logger.info("Gata. Total: %d randuri actualizate.", total_updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
