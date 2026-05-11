"""Preprocess OWID COVID-19 data into per-country compartmental datasets.

For each of 10 countries, this script:
  1. downloads (or reuses cached) the OWID full dataset,
  2. filters to the target country and date window
     (2020-01-22 -> 2023-12-31),
  3. derives observable compartments (infected, removed, susceptible)
     from raw OWID fields,
  4. validates the resulting series,
  5. writes a CSV ready to upload via POST /api/datasets.

Derivation:
  * infected(t) = sum of new_cases over the last INFECTIOUS_WINDOW_DAYS
                  (14 days), approximating the count of active infections
                  at time t.
  * recovered(t) = total_cases(t) - infected(t)
                  -- people no longer infectious (recovered + deceased,
                  the "removed" compartment in SIR; mapped to H in SIDARTH).
  * susceptible(t) = N - infected(t) - recovered(t)   -- by conservation.

The 14-day infectious window matches the clinical estimate for COVID-19
documented in the thesis (gamma = 1/14 ~ 0.0714 day^-1).

The same CSV schema feeds both supported models: SIR uses
(susceptible, infected, recovered) directly as (S0, I0, R0), while
SIDARTH places active infections in compartment I and previously
infected individuals in compartment H, with D, A, R, T starting at zero
(see thesis chapter 5).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests

OWID_URL = "https://covid.ourworldindata.org/data/owid-covid-data.csv"
START_DATE = pd.Timestamp("2020-01-22")
END_DATE = pd.Timestamp("2023-12-31")
INFECTIOUS_WINDOW_DAYS = 14
MAX_GAP_DAYS = 14

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
RAW_FILE = RAW_DIR / "owid-covid-data.csv"


@dataclass(frozen=True)
class Country:
    iso3: str
    name: str
    slug: str


COUNTRIES: tuple[Country, ...] = (
    Country("ROU", "Romania",       "romania"),
    Country("ITA", "Italy",         "italy"),
    Country("KOR", "South Korea",   "south_korea"),
    Country("DEU", "Germany",       "germany"),
    Country("GBR", "United Kingdom","united_kingdom"),
    Country("USA", "United States", "united_states"),
    Country("BRA", "Brazil",        "brazil"),
    Country("SWE", "Sweden",        "sweden"),
    Country("JPN", "Japan",         "japan"),
    Country("IND", "India",         "india"),
)

logger = logging.getLogger("preprocess_owid")


def download_if_missing(force: bool) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_FILE.exists() and not force:
        logger.info("using cached %s (%.1f MB)", RAW_FILE, RAW_FILE.stat().st_size / 1e6)
        return RAW_FILE

    logger.info("downloading %s ...", OWID_URL)
    with requests.get(OWID_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        tmp = RAW_FILE.with_suffix(".csv.part")
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if chunk:
                    fh.write(chunk)
        tmp.replace(RAW_FILE)

    logger.info("downloaded %.1f MB to %s", RAW_FILE.stat().st_size / 1e6, RAW_FILE)
    return RAW_FILE


def load_country(raw_path: Path, iso3: str) -> pd.DataFrame:
    cols = ["iso_code", "location", "date", "new_cases", "total_cases",
            "total_deaths", "population"]
    df = pd.read_csv(
        raw_path,
        usecols=cols,
        parse_dates=["date"],
        dtype={"iso_code": "string", "location": "string"},
    )
    df = df[df["iso_code"] == iso3].copy()
    if df.empty:
        raise ValueError(f"no rows for iso_code={iso3}")
    df = df[(df["date"] >= START_DATE) & (df["date"] <= END_DATE)]
    df = df.sort_values("date").reset_index(drop=True)
    return df


def fill_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """Reindex to a continuous daily calendar; forward-fill cumulatives,
    zero-fill new_cases for missing days."""
    cal = pd.date_range(START_DATE, END_DATE, freq="D")
    df = df.set_index("date").reindex(cal)
    df.index.name = "date"

    df["new_cases"] = df["new_cases"].fillna(0).clip(lower=0)
    for c in ("total_cases", "total_deaths"):
        df[c] = df[c].ffill().fillna(0)

    pop_series = df["population"].dropna()
    if pop_series.empty:
        raise ValueError("population missing entirely")
    df["population"] = pop_series.iloc[0]

    df["iso_code"] = df["iso_code"].ffill().bfill()
    df["location"] = df["location"].ffill().bfill()
    return df.reset_index()


def derive_compartments(df: pd.DataFrame) -> pd.DataFrame:
    population = float(df["population"].iloc[0])

    rolling_new = (
        df["new_cases"]
        .rolling(window=INFECTIOUS_WINDOW_DAYS, min_periods=1)
        .sum()
    )
    infected = rolling_new.clip(lower=0)

    total_cases = df["total_cases"].astype(float)
    removed = (total_cases - infected).clip(lower=0)

    susceptible = (population - infected - removed).clip(lower=0)

    sum_compartments = susceptible + infected + removed
    drift = (sum_compartments - population).abs().max()

    out = pd.DataFrame({
        "date": df["date"].dt.strftime("%Y-%m-%d"),
        "region": df["iso_code"],
        "infected": infected.round().astype("int64"),
        "population": int(population),
        "recovered": removed.round().astype("int64"),
        "susceptible": susceptible.round().astype("int64"),
    })

    logger.debug("max conservation drift (raw): %.4f", drift)
    return out


def validate(df: pd.DataFrame, country: Country) -> None:
    if df["infected"].lt(0).any():
        raise ValueError(f"{country.iso3}: negative infected")
    if df["recovered"].lt(0).any():
        raise ValueError(f"{country.iso3}: negative recovered")
    if df["susceptible"].lt(0).any():
        raise ValueError(f"{country.iso3}: negative susceptible")
    if (df["infected"] + df["recovered"] > df["population"]).any():
        raise ValueError(f"{country.iso3}: I+R exceeds population")

    dates = pd.to_datetime(df["date"])
    if not dates.is_monotonic_increasing:
        raise ValueError(f"{country.iso3}: dates not in chronological order")
    gaps = dates.diff().dropna().dt.days
    if (gaps > MAX_GAP_DAYS).any():
        raise ValueError(
            f"{country.iso3}: gap > {MAX_GAP_DAYS} days between consecutive rows"
        )


def process_country(raw_path: Path, country: Country) -> Path:
    logger.info("[%s] loading ...", country.iso3)
    raw = load_country(raw_path, country.iso3)
    raw = fill_calendar(raw)

    sir = derive_compartments(raw)
    validate(sir, country)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{country.slug}.csv"
    sir.to_csv(out_path, index=False)
    logger.info(
        "[%s] wrote %d rows -> %s  (peak I = %d, N = %d)",
        country.iso3,
        len(sir),
        out_path.relative_to(REPO_ROOT),
        sir["infected"].max(),
        sir["population"].iloc[0],
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preprocess OWID COVID-19 data.")
    parser.add_argument("--force-download", action="store_true",
                        help="re-download raw CSV even if cache exists")
    parser.add_argument("--country", action="append", default=None,
                        help="restrict to specific ISO3 codes (repeatable)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    targets = COUNTRIES
    if args.country:
        wanted = {c.upper() for c in args.country}
        targets = tuple(c for c in COUNTRIES if c.iso3 in wanted)
        if not targets:
            logger.error("no matching countries in %s", wanted)
            return 2

    raw_path = download_if_missing(args.force_download)

    failures: list[str] = []
    for country in targets:
        try:
            process_country(raw_path, country)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] failed: %s", country.iso3, exc)
            failures.append(country.iso3)

    if failures:
        logger.error("failed countries: %s", ", ".join(failures))
        return 1

    logger.info("done. processed %d countries -> %s", len(targets),
                PROCESSED_DIR.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
