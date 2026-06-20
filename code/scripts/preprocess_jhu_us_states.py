"""Preprocesare JHU CSSE COVID-19 — state-uri SUA.

Descarca seriile temporale daily confirmate (confirmed) și deces (deaths) de la
nivel de county SUA, agregă pe state și produce CSV-uri compartimentale per state
în formatul aplicației:

    date, region, infected, population, recovered, susceptible, deaths,
    new_cases, new_deaths

Sursa: Johns Hopkins University Center for Systems Science and Engineering
       (JHU CSSE) — https://github.com/CSSEGISandData/COVID-19
       Datele sunt distribuite sub licență Creative Commons Attribution 4.0
       (CC-BY 4.0) pentru utilizare educațională/de cercetare.

Acoperire temporală: 2020-01-22 → 2023-03-09 (data ultimei actualizări JHU).
Populația per state vine din fișierul lookup oficial UID (Population coloană).

Output: data/processed/jhu_us_states/<state_slug>.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

import epi_common as epi

JHU_BASE = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series"
URL_CONFIRMED = f"{JHU_BASE}/time_series_covid19_confirmed_US.csv"
URL_DEATHS = f"{JHU_BASE}/time_series_covid19_deaths_US.csv"
# Tabela lookup pentru populații per FIPS/state
URL_LOOKUP = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/UID_ISO_FIPS_LookUp_Table.csv"

RAW_DIR = epi.RAW_DIR / "jhu"
OUT_SUBDIR = "jhu_us_states"
INFECTIOUS_WINDOW_DAYS = 14

# Doar cele 50 state + DC. Excludem teritoriile (Puerto Rico etc.) și
# entitățile non-state (Diamond Princess, Grand Princess).
EXCLUDED_PROVINCES = {
    "American Samoa", "Diamond Princess", "Grand Princess",
    "Guam", "Northern Mariana Islands", "Puerto Rico", "Virgin Islands",
}

logger = logging.getLogger("preprocess_jhu_us_states")


def slug_of(state: str) -> str:
    return state.lower().replace(" ", "_").replace(".", "")


def fetch_inputs(force: bool) -> tuple[Path, Path, Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    confirmed = epi.download_if_missing(URL_CONFIRMED, RAW_DIR / "time_series_confirmed_US.csv", force)
    deaths = epi.download_if_missing(URL_DEATHS, RAW_DIR / "time_series_deaths_US.csv", force)
    lookup = epi.download_if_missing(URL_LOOKUP, RAW_DIR / "UID_lookup.csv", force)
    return confirmed, deaths, lookup


def load_state_populations(lookup_path: Path) -> dict[str, int]:
    """Populația per state din lookup-ul oficial JHU (entități cu Admin2=NaN)."""
    df = pd.read_csv(lookup_path)
    # State-level rows au country = US, Admin2 = NaN, Province_State setat
    states = df[(df["Country_Region"] == "US") & df["Admin2"].isna() & df["Province_State"].notna()]
    out: dict[str, int] = {}
    for _, row in states.iterrows():
        state = str(row["Province_State"]).strip()
        if state in EXCLUDED_PROVINCES:
            continue
        pop = row.get("Population")
        if pd.isna(pop) or pop <= 0:
            continue
        out[state] = int(pop)
    return out


def melt_jhu(time_series_path: Path) -> pd.DataFrame:
    """Convertește JHU wide-form (o coloană per zi) în long-form (state, date, value).

    Agregat la nivel de state (sum pe counties).
    """
    df = pd.read_csv(time_series_path)
    # Coloane meta JHU: UID, iso2, iso3, code3, FIPS, Admin2, Province_State,
    # Country_Region, Lat, Long_, Combined_Key, [Population pt deaths], 1/22/20, ...
    meta_cols = {"UID", "iso2", "iso3", "code3", "FIPS", "Admin2", "Province_State",
                 "Country_Region", "Lat", "Long_", "Combined_Key", "Population"}
    date_cols = [c for c in df.columns if c not in meta_cols]
    long = df.melt(
        id_vars=["Province_State"],
        value_vars=date_cols,
        var_name="date_str",
        value_name="value",
    )
    long["date"] = pd.to_datetime(long["date_str"], format="%m/%d/%y", errors="coerce")
    long = long.dropna(subset=["date"])
    # Sum pe state (peste counties)
    agg = long.groupby(["Province_State", "date"], as_index=False)["value"].sum()
    return agg.rename(columns={"Province_State": "state"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    confirmed_path, deaths_path, lookup_path = fetch_inputs(args.force_download)
    pop = load_state_populations(lookup_path)
    logger.info("Populații încărcate pentru %d state-uri", len(pop))

    confirmed = melt_jhu(confirmed_path).rename(columns={"value": "total_cases"})
    deaths = melt_jhu(deaths_path).rename(columns={"value": "total_deaths"})

    merged = confirmed.merge(deaths, on=["state", "date"], how="inner")

    start = pd.Timestamp("2020-01-22")
    end = pd.Timestamp("2023-03-09")
    out_dir = epi.PROCESSED_DIR / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for state, pop_n in sorted(pop.items()):
        sub = merged[merged["state"] == state].copy()
        if sub.empty:
            continue
        sub["population"] = pop_n
        sub["region"] = "US-" + state[:3].upper()  # cod scurt, ex: US-CAL
        # JHU dă cumulativi → derivăm new_cases / new_deaths
        sub = sub.sort_values("date").reset_index(drop=True)
        sub["new_cases"] = sub["total_cases"].diff().clip(lower=0).fillna(0).astype(int)
        sub["new_deaths"] = sub["total_deaths"].diff().clip(lower=0).fillna(0).astype(int)
        sub = sub[(sub["date"] >= start) & (sub["date"] <= end)]
        if sub.empty:
            continue

        # Calendar zilnic continuu
        sub = epi.fill_calendar(sub, start, end)
        # Derivare compartimente standard
        out = epi.derive_compartments(sub, INFECTIOUS_WINDOW_DAYS)
        try:
            epi.validate(out, state)
        except Exception as e:  # noqa: BLE001
            logger.warning("[%s] validare eșuată: %s", state, e)
            continue
        out_path = out_dir / f"{slug_of(state)}.csv"
        out.to_csv(out_path, index=False)
        generated += 1
        logger.info("[%s] %d zile -> %s (pop=%d)", state, len(out), out_path.name, pop_n)

    logger.info("Gata: %d state-uri scrise în %s",
                generated, out_dir.relative_to(epi.REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
