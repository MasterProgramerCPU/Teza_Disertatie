"""Split JHU CSSE Global Province_State în CSV-uri per-regiune (1 dataset/regiune).

Pentru USA avem deja JHU US states (51 fișiere separate). Pentru Romania avem
ro_judete (42 fișiere). Acest script generează același format per-regiune
pentru China, Canada, Australia, France din JHU CSSE Global.

Output: data/processed/<country>_subdiv/<code>.csv

Acest format permite hărții să afișeze per-regiune corect (1 simulare per
regiune = 1 culoare per regiune pe hartă).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

import epi_common as epi

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

# Reutilizez mapările + populațiile din combine_subnational
from combine_subnational import (  # noqa: E402
    SUBDIV_CODES, POPULATIONS, COUNTRY_ISO3,
    fetch_jhu_global, melt_global,
)

logger = logging.getLogger("split_jhu")


def build_region_csv(confirmed: pd.DataFrame, deaths: pd.DataFrame,
                     country: str, province: str, code: str, pop: int) -> pd.DataFrame:
    sub_c = confirmed[(confirmed["Country/Region"] == country) &
                      (confirmed["Province/State"] == province)]
    sub_d = deaths[(deaths["Country/Region"] == country) &
                   (deaths["Province/State"] == province)]
    if sub_c.empty:
        return pd.DataFrame()
    long_c = melt_global(sub_c, "total_cases")
    long_d = melt_global(sub_d, "total_deaths")
    df = long_c.merge(long_d, on=["Province/State", "Country/Region", "date"], how="left")
    df = df.sort_values("date").reset_index(drop=True)
    df["new_cases"] = df["total_cases"].diff().clip(lower=0).fillna(0).astype("int64")
    df["new_deaths"] = df["total_deaths"].diff().clip(lower=0).fillna(0).astype("int64")
    df["total_cases"] = df["total_cases"].fillna(0).astype("int64")
    df["total_deaths"] = df["total_deaths"].fillna(0).astype("int64")
    df["region"] = code
    df["population"] = pop
    df["infected"] = df["new_cases"].rolling(window=14, min_periods=1).sum().astype("int64")
    df["recovered"] = (df["total_cases"] - df["infected"]).clip(lower=0).astype("int64")
    df["susceptible"] = (pop - df["infected"] - df["recovered"]).clip(lower=0).astype("int64")
    df["deaths"] = df["total_deaths"]
    return df[[
        "date", "region", "infected", "population", "recovered",
        "susceptible", "deaths", "new_cases", "new_deaths",
    ]]


def main() -> int:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    confirmed, deaths = fetch_jhu_global()

    for country, iso3 in COUNTRY_ISO3.items():
        out_dir = PROCESSED / f"{iso3.lower()}_subdiv"
        out_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for (cn, province), code in SUBDIV_CODES.items():
            if cn != country:
                continue
            pop = POPULATIONS.get(code)
            if not pop:
                continue
            df = build_region_csv(confirmed, deaths, country, province, code, pop)
            if df.empty:
                continue
            out_path = out_dir / f"{code}.csv"
            df.to_csv(out_path, index=False)
            count += 1
        logger.info("[%s] %d CSV-uri scrise în %s", country, count, out_dir.relative_to(epi.REPO_ROOT))

    logger.info("Gata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
