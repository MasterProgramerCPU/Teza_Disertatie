"""Preprocesare OWID COVID-19 — TOATE țările din setul brut.

Spre deosebire de :mod:`preprocess_owid` (lista curata de 64 țări selectate
pentru benchmark), acest script procesează **toate** codurile ISO3 disponibile
în CSV-ul OWID (~237 țări/teritorii). Output-ul ajunge în
``data/processed/owid_all/<iso3>.csv`` și e folosit pentru seed-urile
„COVID-19 — World OWID complet" care urmăresc să umple baza de date cu volum
mare provenit din sursă reală publică.

Sursa: https://github.com/owid/covid-19-data (CC-BY 4.0)

Filtrăm țările care:
  • au cel puțin 100 zile de raportare nenule (altfel nu se poate construi
    o serie SIR rezonabilă),
  • au populație raportată > 0,
  • nu sunt agregate regionale OWID (cod ISO3 lipsă/non-standard).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

import epi_common as epi

OWID_URL = "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv"
START_DATE = pd.Timestamp("2020-01-22")
END_DATE = pd.Timestamp("2023-12-31")
INFECTIOUS_WINDOW_DAYS = 14

RAW_FILE = epi.RAW_DIR / "owid-covid-data.csv"
OUT_SUBDIR = "owid_all"

# Agregate OWID (regionale, World, income groups). Le excludem ca să avem
# doar țări/teritorii reale.
AGGREGATE_ISO3_PATTERNS = {
    "OWID_WRL",  # World
    "OWID_AFR", "OWID_ASI", "OWID_EUR", "OWID_NAM", "OWID_SAM", "OWID_OCE",
    "OWID_EUN",  # European Union
    "OWID_HIC", "OWID_UMC", "OWID_LMC", "OWID_LIC",  # income groups
    "OWID_INT",  # International (cruise ships etc.)
    "OWID_KOS",  # Kosovo handled separately in OWID
    "OWID_CYN",  # Northern Cyprus
}

logger = logging.getLogger("preprocess_owid_all")


def slug_of(iso3: str) -> str:
    """Slug stabil pentru numele fișierului — folosim ISO3 lowercase."""
    return iso3.lower()


def list_iso3(raw_path: Path) -> list[str]:
    """Citește doar coloana iso_code și întoarce lista unică de ISO3 valide."""
    df = pd.read_csv(raw_path, usecols=["iso_code"], dtype={"iso_code": "string"})
    iso3s = df["iso_code"].dropna().unique().tolist()
    # Standardul ISO3 = exact 3 litere majuscule. Excludem agregatele OWID.
    out = []
    for c in iso3s:
        c = str(c).strip()
        if len(c) != 3 or not c.isalpha() or not c.isupper():
            continue
        if c in AGGREGATE_ISO3_PATTERNS:
            continue
        out.append(c)
    return sorted(out)


def process_country(raw_path: Path, iso3: str) -> bool:
    """Returnează True dacă a generat fișier, False dacă a sărit (date insuficiente)."""
    cols = [
        "iso_code", "date", "new_cases", "total_cases", "population",
        "total_deaths", "new_deaths",
        "hosp_patients", "icu_patients",
        "people_vaccinated", "total_tests",
        "stringency_index", "reproduction_rate",
    ]
    df = pd.read_csv(
        raw_path,
        usecols=lambda c: c in cols,
        parse_dates=["date"],
        dtype={"iso_code": "string"},
    )
    df = df[df["iso_code"] == iso3].copy()
    if df.empty:
        return False
    df = df[(df["date"] >= START_DATE) & (df["date"] <= END_DATE)]
    if df.empty:
        return False

    # Validare minimă: populație nenulă și suficiente zile de raportare
    pop_series = df["population"].dropna()
    if pop_series.empty or pop_series.iloc[0] <= 0:
        return False
    nonzero_days = (df["new_cases"].fillna(0) > 0).sum()
    if nonzero_days < 100:
        return False

    df = df.rename(columns={"iso_code": "region"})
    df = df.sort_values("date").reset_index(drop=True)
    df = epi.fill_calendar(df, START_DATE, END_DATE)
    out = epi.derive_compartments(df, INFECTIOUS_WINDOW_DAYS)
    try:
        epi.validate(out, iso3)
    except Exception as e:  # noqa: BLE001
        logger.warning("[%s] validare eșuată: %s", iso3, e)
        return False

    # Output în subdirectorul dedicat — separat de cele 64 țări curate
    out_dir = epi.PROCESSED_DIR / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slug_of(iso3)}.csv"
    out.to_csv(out_path, index=False)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    raw_path = epi.download_if_missing(OWID_URL, RAW_FILE, args.force_download)
    iso3_list = list_iso3(raw_path)
    logger.info("Plan: %d coduri ISO3 candidate", len(iso3_list))

    generated, skipped = 0, 0
    for iso3 in iso3_list:
        try:
            if process_country(raw_path, iso3):
                generated += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] eroare: %s", iso3, exc)
            skipped += 1

    logger.info(
        "Gata: %d CSV-uri scrise în %s (%d sărite din lipsă de date)",
        generated,
        (epi.PROCESSED_DIR / OUT_SUBDIR).relative_to(epi.REPO_ROOT),
        skipped,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
