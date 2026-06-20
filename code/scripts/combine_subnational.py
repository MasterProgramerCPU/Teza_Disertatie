"""Combină datele sub-naționale în CSV-uri „mari" per țară (10k+ rânduri).

Pentru fiecare țară mare cu date sub-naționale publice disponibile, produce
un singur CSV care conține câte un rând per (zi × subdiviziune). Codurile
de regiune urmează ISO 3166-2 (ex: RO-CJ, US-CA, CN-HB).

Surse:
  • USA — 50 state-uri + DC din JHU CSSE US states (preprocesate în
    data/processed/jhu_us_states/)
  • Romania — 42 județe din generate_romania_counties.py (sintetic distribuit
    din OWID național)
  • China, Canada, UK, France, Australia — JHU CSSE Global time series
    (Province_State, sub-national)

Output: data/processed/subnational/<iso3>.csv

Fiecare CSV are 10k+ rânduri (zile × subdiviziuni) și e încărcat în aplicație
ca un singur dataset per țară.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

import epi_common as epi

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT_DIR = PROCESSED / "subnational"

logger = logging.getLogger("combine_subnational")


# Mapare nume Province_State JHU -> cod ISO 3166-2.
# Sursă: ISO online browsing platform + Wikipedia "ISO 3166-2:<CC>".
SUBDIV_CODES: dict[tuple[str, str], str] = {
    # China — provincii + municipalități
    ("China", "Anhui"): "CN-AH", ("China", "Beijing"): "CN-BJ",
    ("China", "Chongqing"): "CN-CQ", ("China", "Fujian"): "CN-FJ",
    ("China", "Gansu"): "CN-GS", ("China", "Guangdong"): "CN-GD",
    ("China", "Guangxi"): "CN-GX", ("China", "Guizhou"): "CN-GZ",
    ("China", "Hainan"): "CN-HI", ("China", "Hebei"): "CN-HE",
    ("China", "Heilongjiang"): "CN-HL", ("China", "Henan"): "CN-HA",
    ("China", "Hong Kong"): "CN-HK", ("China", "Hubei"): "CN-HB",
    ("China", "Hunan"): "CN-HN", ("China", "Inner Mongolia"): "CN-NM",
    ("China", "Jiangsu"): "CN-JS", ("China", "Jiangxi"): "CN-JX",
    ("China", "Jilin"): "CN-JL", ("China", "Liaoning"): "CN-LN",
    ("China", "Macau"): "CN-MO", ("China", "Ningxia"): "CN-NX",
    ("China", "Qinghai"): "CN-QH", ("China", "Shaanxi"): "CN-SN",
    ("China", "Shandong"): "CN-SD", ("China", "Shanghai"): "CN-SH",
    ("China", "Shanxi"): "CN-SX", ("China", "Sichuan"): "CN-SC",
    ("China", "Tianjin"): "CN-TJ", ("China", "Tibet"): "CN-XZ",
    ("China", "Xinjiang"): "CN-XJ", ("China", "Yunnan"): "CN-YN",
    ("China", "Zhejiang"): "CN-ZJ",
    # Canada — provincii + teritorii
    ("Canada", "Alberta"): "CA-AB", ("Canada", "British Columbia"): "CA-BC",
    ("Canada", "Manitoba"): "CA-MB", ("Canada", "New Brunswick"): "CA-NB",
    ("Canada", "Newfoundland and Labrador"): "CA-NL",
    ("Canada", "Northwest Territories"): "CA-NT",
    ("Canada", "Nova Scotia"): "CA-NS", ("Canada", "Nunavut"): "CA-NU",
    ("Canada", "Ontario"): "CA-ON",
    ("Canada", "Prince Edward Island"): "CA-PE",
    ("Canada", "Quebec"): "CA-QC", ("Canada", "Saskatchewan"): "CA-SK",
    ("Canada", "Yukon"): "CA-YT",
    # United Kingdom — națiuni constituente
    ("United Kingdom", ""): "GB-ENG",  # mainland row în JHU (Province_State NaN)
    # JHU UK „națiuni": vom prefera coduri ISO atunci când Province e setat
    # (overseas territories au coduri proprii)
    # Australia — state + teritorii
    ("Australia", "Australian Capital Territory"): "AU-ACT",
    ("Australia", "New South Wales"): "AU-NSW",
    ("Australia", "Northern Territory"): "AU-NT",
    ("Australia", "Queensland"): "AU-QLD",
    ("Australia", "South Australia"): "AU-SA",
    ("Australia", "Tasmania"): "AU-TAS",
    ("Australia", "Victoria"): "AU-VIC",
    ("Australia", "Western Australia"): "AU-WA",
    # France — DOM/TOM (mainland are Province_State gol)
    ("France", "French Guiana"): "FR-GF",
    ("France", "French Polynesia"): "FR-PF",
    ("France", "Guadeloupe"): "FR-GP",
    ("France", "Martinique"): "FR-MQ",
    ("France", "Mayotte"): "FR-YT",
    ("France", "New Caledonia"): "FR-NC",
    ("France", "Reunion"): "FR-RE",
    ("France", "Saint Barthelemy"): "FR-BL",
    ("France", "Saint Pierre and Miquelon"): "FR-PM",
    ("France", "St Martin"): "FR-MF",
    ("France", "Wallis and Futuna"): "FR-WF",
}

# Populații estimate (date publice; folosit pentru completare în CSV).
# Surse: National statistical offices + World Bank 2021.
POPULATIONS: dict[str, int] = {
    # China provinces (2020 census approximate)
    "CN-AH": 61027000, "CN-BJ": 21893000, "CN-CQ": 32054000,
    "CN-FJ": 41540000, "CN-GS": 25019000, "CN-GD": 126010000,
    "CN-GX": 50127000, "CN-GZ": 38560000, "CN-HI": 10081000,
    "CN-HE": 74610000, "CN-HL": 31851000, "CN-HA": 99366000,
    "CN-HK": 7414000,  "CN-HB": 57752000, "CN-HN": 66444000,
    "CN-NM": 24049000, "CN-JS": 84748000, "CN-JX": 45188000,
    "CN-JL": 24073000, "CN-LN": 42591000, "CN-MO": 683000,
    "CN-NX": 7202000,  "CN-QH": 5923000,  "CN-SN": 39528000,
    "CN-SD": 101526000,"CN-SH": 24871000, "CN-SX": 34915000,
    "CN-SC": 83674000, "CN-TJ": 13866000, "CN-XZ": 3648000,
    "CN-XJ": 25852000, "CN-YN": 47209000, "CN-ZJ": 64567000,
    # Canada (StatCan 2021)
    "CA-AB": 4262635, "CA-BC": 5000879, "CA-MB": 1342153,
    "CA-NB": 775610, "CA-NL": 510550, "CA-NT": 41070,
    "CA-NS": 969383, "CA-NU": 36858, "CA-ON": 14223942,
    "CA-PE": 154331, "CA-QC": 8501833, "CA-SK": 1132505,
    "CA-YT": 40232,
    # Australia (ABS 2021)
    "AU-ACT": 431826, "AU-NSW": 8166369, "AU-NT": 246338,
    "AU-QLD": 5184847, "AU-SA": 1771703, "AU-TAS": 557571,
    "AU-VIC": 6648564, "AU-WA": 2681633,
    # France overseas (INSEE 2021)
    "FR-GF": 290691, "FR-PF": 278786, "FR-GP": 384239,
    "FR-MQ": 364508, "FR-YT": 288926, "FR-NC": 270875,
    "FR-RE": 855961, "FR-BL": 9961, "FR-PM": 5800,
    "FR-MF": 32489, "FR-WF": 11369,
}


# Mapare ISO3 -> nume țară JHU global
COUNTRY_ISO3 = {
    "China": "CHN", "Canada": "CAN",
    "Australia": "AUS", "France": "FRA",
}


def fetch_jhu_global() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descarcă (sau citește cache) seriile JHU confirmed/deaths global."""
    base = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series"
    raw_dir = epi.RAW_DIR / "jhu"
    raw_dir.mkdir(parents=True, exist_ok=True)
    confirmed_path = epi.download_if_missing(
        f"{base}/time_series_covid19_confirmed_global.csv",
        raw_dir / "time_series_confirmed_global.csv", False,
    )
    deaths_path = epi.download_if_missing(
        f"{base}/time_series_covid19_deaths_global.csv",
        raw_dir / "time_series_deaths_global.csv", False,
    )
    confirmed = pd.read_csv(confirmed_path)
    deaths = pd.read_csv(deaths_path)
    return confirmed, deaths


def melt_global(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Wide -> long pentru JHU global time series."""
    meta = {"Province/State", "Country/Region", "Lat", "Long"}
    date_cols = [c for c in df.columns if c not in meta]
    long = df.melt(
        id_vars=["Province/State", "Country/Region"],
        value_vars=date_cols,
        var_name="date_str",
        value_name=value_name,
    )
    long["date"] = pd.to_datetime(long["date_str"], format="%m/%d/%y", errors="coerce")
    long = long.dropna(subset=["date"])
    return long.drop(columns=["date_str"])


def build_jhu_country(confirmed: pd.DataFrame, deaths: pd.DataFrame,
                      country: str, iso3: str) -> pd.DataFrame | None:
    """Construiește seria long pentru o țară cu subdiviziuni JHU.

    Output: coloanele standard ale schemei aplicației.
    """
    sub_confirmed = confirmed[confirmed["Country/Region"] == country].copy()
    sub_deaths = deaths[deaths["Country/Region"] == country].copy()
    # Excludem rândul mainland (Province_State NaN) — îl tratăm separat dacă vrem
    sub_confirmed = sub_confirmed[sub_confirmed["Province/State"].notna()]
    sub_deaths = sub_deaths[sub_deaths["Province/State"].notna()]
    if sub_confirmed.empty:
        return None

    long_c = melt_global(sub_confirmed, "total_cases")
    long_d = melt_global(sub_deaths, "total_deaths")
    df = long_c.merge(long_d, on=["Province/State", "Country/Region", "date"], how="left")

    # Aplicăm mapare ISO 3166-2
    df["region_code"] = df.apply(
        lambda r: SUBDIV_CODES.get((country, r["Province/State"])), axis=1,
    )
    df = df.dropna(subset=["region_code"])
    if df.empty:
        return None

    df["population"] = df["region_code"].map(POPULATIONS).fillna(0).astype("int64")
    df = df[df["population"] > 0]
    if df.empty:
        return None

    # Sortăm și derivăm new_cases / new_deaths per region
    df = df.sort_values(["region_code", "date"]).reset_index(drop=True)
    df["new_cases"] = (df.groupby("region_code")["total_cases"]
                         .diff().clip(lower=0).fillna(0).astype("int64"))
    df["new_deaths"] = (df.groupby("region_code")["total_deaths"]
                          .diff().clip(lower=0).fillna(0).astype("int64"))
    df["total_cases"] = df["total_cases"].fillna(0).astype("int64")
    df["total_deaths"] = df["total_deaths"].fillna(0).astype("int64")

    # Calcul fereastră infecțioasă 14 zile per regiune
    df["infected"] = (df.groupby("region_code")["new_cases"]
                        .transform(lambda s: s.rolling(window=14, min_periods=1).sum())
                        .astype("int64"))
    df["recovered"] = (df["total_cases"] - df["infected"]).clip(lower=0).astype("int64")
    df["susceptible"] = (df["population"] - df["infected"] - df["recovered"]).clip(lower=0).astype("int64")

    df["deaths"] = df["total_deaths"]
    out = df[[
        "date", "region_code", "infected", "population", "recovered",
        "susceptible", "deaths", "new_cases", "new_deaths",
    ]].rename(columns={"region_code": "region"})
    return out.sort_values(["date", "region"], kind="mergesort").reset_index(drop=True)


def combine_state_csvs(src_dir: Path, region_prefix: str) -> pd.DataFrame:
    """Combină CSV-uri per-state într-un singur dataframe cu region_code mapate.

    Sortarea finală e (date ascendent, region) — API-ul refuză dates
    descrescătoare, dar acceptă repetate (multiple regiuni pe aceeași zi).
    """
    rows = []
    for path in sorted(src_dir.glob("*.csv")):
        df = pd.read_csv(path)
        if df.empty:
            continue
        keep = ["date", "region", "infected", "population", "recovered",
                "susceptible", "deaths", "new_cases", "new_deaths",
                "hospitalized", "icu", "vaccinated", "tested",
                "stringency_index", "reproduction_rate"]
        for col in keep:
            if col not in df.columns:
                df[col] = ""
        rows.append(df[keep])
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    # Convertim coloanele numerice care pot avea float-strings ("71.0") la int
    for col in ("infected", "population", "recovered", "susceptible",
                "deaths", "new_cases", "new_deaths",
                "hospitalized", "icu", "vaccinated", "tested"):
        if col in out.columns:
            out[col] = (
                pd.to_numeric(out[col], errors="coerce")
                  .fillna(0).round().astype("Int64")
            )
    # Float-uri pentru indici rămân float
    for col in ("stringency_index", "reproduction_rate"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values(["date", "region"], kind="mergesort").reset_index(drop=True)


def write_csv(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. USA — combine cele 51 CSV-uri JHU US state-uri
    src_us = PROCESSED / "jhu_us_states"
    if src_us.exists():
        df_us = combine_state_csvs(src_us, "US")
        if not df_us.empty:
            # Reformatăm region la US-XX (ISO 3166-2)
            # Codurile original sunt "US-NEW" (luate din state name) — refacem corect.
            STATE_CODES = {
                "Alabama": "US-AL", "Alaska": "US-AK", "Arizona": "US-AZ", "Arkansas": "US-AR",
                "California": "US-CA", "Colorado": "US-CO", "Connecticut": "US-CT",
                "Delaware": "US-DE", "District of Columbia": "US-DC", "Florida": "US-FL",
                "Georgia": "US-GA", "Hawaii": "US-HI", "Idaho": "US-ID", "Illinois": "US-IL",
                "Indiana": "US-IN", "Iowa": "US-IA", "Kansas": "US-KS", "Kentucky": "US-KY",
                "Louisiana": "US-LA", "Maine": "US-ME", "Maryland": "US-MD",
                "Massachusetts": "US-MA", "Michigan": "US-MI", "Minnesota": "US-MN",
                "Mississippi": "US-MS", "Missouri": "US-MO", "Montana": "US-MT",
                "Nebraska": "US-NE", "Nevada": "US-NV", "New Hampshire": "US-NH",
                "New Jersey": "US-NJ", "New Mexico": "US-NM", "New York": "US-NY",
                "North Carolina": "US-NC", "North Dakota": "US-ND", "Ohio": "US-OH",
                "Oklahoma": "US-OK", "Oregon": "US-OR", "Pennsylvania": "US-PA",
                "Rhode Island": "US-RI", "South Carolina": "US-SC", "South Dakota": "US-SD",
                "Tennessee": "US-TN", "Texas": "US-TX", "Utah": "US-UT", "Vermont": "US-VT",
                "Virginia": "US-VA", "Washington": "US-WA", "West Virginia": "US-WV",
                "Wisconsin": "US-WI", "Wyoming": "US-WY",
            }
            # CSV-urile au numele state-ului în slug. Le mapăm la ISO 3166-2.
            slug_to_iso = {k.lower().replace(" ", "_"): v for k, v in STATE_CODES.items()}
            # Reconstituim slug din fiecare CSV
            usa_rows = []
            for path in sorted(src_us.glob("*.csv")):
                slug = path.stem
                code = slug_to_iso.get(slug)
                if not code:
                    continue
                d = pd.read_csv(path)
                if d.empty:
                    continue
                d["region"] = code
                usa_rows.append(d)
            df_us = pd.concat(usa_rows, ignore_index=True)
            # Normalizam numerele float-as-strings la int (pt coloane epi);
            # API-ul refuza "71.0" pentru coloana tested.
            for col in ("infected", "population", "recovered", "susceptible",
                        "deaths", "new_cases", "new_deaths",
                        "hospitalized", "icu", "vaccinated", "tested"):
                if col in df_us.columns:
                    df_us[col] = (pd.to_numeric(df_us[col], errors="coerce")
                                    .fillna(0).round().astype("Int64"))
            # Sortare cronologică (API refuză date descendente; acceptă repetate)
            df_us = df_us.sort_values(["date", "region"], kind="mergesort").reset_index(drop=True)
            write_csv(df_us, OUT_DIR / "usa.csv")
            logger.info("USA: %d rânduri (51 state-uri × ~1143 zile)", len(df_us))

    # 2. Romania — combine cele 42 CSV-uri din ro_judete (codurile sunt deja RO-XX)
    src_ro = PROCESSED / "ro_judete"
    if src_ro.exists():
        df_ro = combine_state_csvs(src_ro, "RO")
        if not df_ro.empty:
            write_csv(df_ro, OUT_DIR / "romania.csv")
            logger.info("Romania: %d rânduri (42 județe × ~1440 zile)", len(df_ro))

    # 3. China, Canada, Australia, France din JHU global
    confirmed, deaths = fetch_jhu_global()
    for country, iso3 in COUNTRY_ISO3.items():
        df = build_jhu_country(confirmed, deaths, country, iso3)
        if df is None or df.empty:
            logger.warning("[%s] niciun subdiv valid", country)
            continue
        slug = iso3.lower()
        write_csv(df, OUT_DIR / f"{slug}.csv")
        logger.info("%s: %d rânduri (%d subdiv × ~%d zile)",
                    country, len(df), df["region"].nunique(),
                    len(df) // max(df["region"].nunique(), 1))

    logger.info("Gata. Fișierele combinate sunt în %s",
                OUT_DIR.relative_to(epi.REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
