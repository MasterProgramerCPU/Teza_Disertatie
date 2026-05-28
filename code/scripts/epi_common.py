"""Logica comuna de preprocesare epidemiologica.

Transforma serii brute (cazuri noi si cumulate + populatie) in schema CSV
compartimentala folosita de aplicatie:

    date, region, infected, population, recovered, susceptible

Sursele concrete (OWID COVID-19, OWID mpox, ...) se ocupa doar de descarcarea
si incarcarea datelor brute, apoi deleaga aici derivarea compartimentelor,
validarea si scrierea. Astfel logica de derivare ramane identica intre surse,
iar un script nou de sursa trebuie sa produca doar un DataFrame cu coloanele
``date``, ``region``, ``new_cases``, ``total_cases`` si ``population``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

logger = logging.getLogger("epi_preprocess")


def download_if_missing(url: str, dest: Path, force: bool) -> Path:
    """Descarca ``url`` in ``dest`` daca lipseste sau daca ``force`` e activ."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("folosesc cache %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
        return dest

    logger.info("descarc %s ...", url)
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
        tmp.replace(dest)

    logger.info("descarcat %.1f MB -> %s", dest.stat().st_size / 1e6, dest)
    return dest


def fill_calendar(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Reindexeaza pe un calendar zilnic continuu intre ``start`` si ``end``.

    Cumulativii (``total_cases``) si ``population`` sunt completati prin
    forward-fill; zilele fara raportare primesc ``new_cases = 0``; valorile
    negative din ``new_cases`` (ajustari retrospective ale raportarilor) sunt
    taiate la zero.

    ``df`` trebuie sa contina coloana ``date`` si coloanele ``new_cases``,
    ``total_cases``, ``population``, ``region``.
    """
    cal = pd.date_range(start, end, freq="D")
    df = df.set_index("date").reindex(cal)
    df.index.name = "date"

    df["new_cases"] = df["new_cases"].fillna(0).clip(lower=0)
    df["total_cases"] = df["total_cases"].ffill().fillna(0)

    pop = df["population"].dropna()
    if pop.empty:
        raise ValueError("population missing entirely")
    df["population"] = float(pop.iloc[0])

    df["region"] = df["region"].ffill().bfill()

    # Pentru coloanele extinse: cumulativele se completeaza prin forward-fill,
    # rate-urile zilnice raman ca atare (NaN cand lipseste raportarea).
    cumulative_cols = ["total_deaths", "people_vaccinated", "total_tests"]
    for col in cumulative_cols:
        if col in df.columns:
            df[col] = df[col].ffill()
    return df.reset_index()


def derive_compartments(df: pd.DataFrame, infectious_window: int) -> pd.DataFrame:
    """Deriva (infected, recovered, susceptible) si pastreaza coloanele extinse.

    * ``infected(t)``    = suma ``new_cases`` pe ultimele ``infectious_window`` zile
      (aproximeaza numarul de infectii active la momentul ``t``);
    * ``recovered(t)``   = ``total_cases(t) - infected(t)`` (compartimentul "removed");
    * ``susceptible(t)`` = ``population - infected - recovered`` (prin conservare).

    Pe langa coloanele SIR-centrice, propaga (cand sunt in df) metricile extinse
    folosite de scripturile user: deaths, new_cases, new_deaths, hospitalized,
    icu, vaccinated, tested, stringency_index, reproduction_rate. Coloanele
    lipsa raman absente in CSV (parser-ul API le trateaza ca optionale).

    ``df`` este iesirea lui :func:`fill_calendar` (calendar zilnic continuu).
    """
    population = float(df["population"].iloc[0])

    rolling_new = df["new_cases"].rolling(window=infectious_window, min_periods=1).sum()
    infected = rolling_new.clip(lower=0)
    removed = (df["total_cases"].astype(float) - infected).clip(lower=0)
    susceptible = (population - infected - removed).clip(lower=0)

    out = pd.DataFrame({
        "date": df["date"].dt.strftime("%Y-%m-%d"),
        "region": df["region"],
        "infected": infected.round().astype("int64"),
        "population": int(population),
        "recovered": removed.round().astype("int64"),
        "susceptible": susceptible.round().astype("int64"),
    })

    # Coloane extinse — propagate doar daca exista in input.
    # Tipurile: int64 cu NA suportat (Pandas Int64), respectiv float64.
    int_mappings = [
        ("deaths", "total_deaths"),
        ("new_cases", "new_cases"),
        ("new_deaths", "new_deaths"),
        ("hospitalized", "hosp_patients"),
        ("icu", "icu_patients"),
        ("vaccinated", "people_vaccinated"),
        ("tested", "total_tests"),
    ]
    for out_col, src_col in int_mappings:
        if src_col in df.columns:
            series = pd.to_numeric(df[src_col], errors="coerce")
            out[out_col] = series.round().astype("Int64")

    for out_col, src_col in [
        ("stringency_index", "stringency_index"),
        ("reproduction_rate", "reproduction_rate"),
    ]:
        if src_col in df.columns:
            out[out_col] = pd.to_numeric(df[src_col], errors="coerce").astype("Float64")

    return out


def validate(df: pd.DataFrame, label: str) -> None:
    """Verifica invariantele schemei comune inainte de scriere."""
    for col in ("infected", "recovered", "susceptible"):
        if df[col].lt(0).any():
            raise ValueError(f"{label}: valori negative in {col}")
    if (df["infected"] + df["recovered"] > df["population"]).any():
        raise ValueError(f"{label}: I+R depaseste populatia")
    if not pd.to_datetime(df["date"]).is_monotonic_increasing:
        raise ValueError(f"{label}: datele nu sunt in ordine cronologica")
    if len(df) < 2:
        raise ValueError(f"{label}: mai putin de 2 inregistrari")


def write_processed(df: pd.DataFrame, slug: str) -> Path:
    """Scrie DataFrame-ul derivat in ``data/processed/<slug>.csv``."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{slug}.csv"
    df.to_csv(out_path, index=False)
    return out_path
