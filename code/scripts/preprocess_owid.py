"""Preprocesare OWID COVID-19 -> seturi de date compartimentale per tara.

Pentru fiecare tara configurata, scriptul:
  1. descarca (sau reutilizeaza cache-ul) setul complet OWID COVID-19,
  2. filtreaza la tara si la fereastra de timp (2020-01-22 -> 2023-12-31),
  3. deriva compartimentele observabile (infected, removed, susceptible) prin
     :mod:`epi_common`,
  4. valideaza seria rezultata,
  5. scrie un CSV gata de incarcat prin POST /api/studies/{studyId}/datasets.

Derivare (vezi :mod:`epi_common`):
  * infected(t)    = suma new_cases pe ultimele INFECTIOUS_WINDOW_DAYS zile;
  * recovered(t)   = total_cases(t) - infected(t)  (compartimentul "removed");
  * susceptible(t) = N - infected(t) - recovered(t).

Fereastra infectioasa de 14 zile corespunde estimarii clinice pentru COVID-19
folosita in lucrare (gamma = 1/14 ~ 0.0714 zi^-1).

Lista de tari acopera deliberat scari de populatie si dinamici epidemice foarte
diferite (Europa + America + Asia + Africa + Oceania), pentru ca benchmark-ul
solverelor sa fie evaluat pe regimuri variate, nu doar pe un singur tipar.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

import pandas as pd

import epi_common as epi

OWID_URL = "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv"
START_DATE = pd.Timestamp("2020-01-22")
END_DATE = pd.Timestamp("2023-12-31")
INFECTIOUS_WINDOW_DAYS = 14

RAW_FILE = epi.RAW_DIR / "owid-covid-data.csv"

logger = logging.getLogger("preprocess_owid")


@dataclass(frozen=True)
class Country:
    iso3: str
    name: str
    slug: str


COUNTRIES: tuple[Country, ...] = (
    # --- UE 27 ---
    Country("AUT", "Austria",        "austria"),
    Country("BEL", "Belgium",        "belgium"),
    Country("BGR", "Bulgaria",       "bulgaria"),
    Country("HRV", "Croatia",        "croatia"),
    Country("CYP", "Cyprus",         "cyprus"),
    Country("CZE", "Czechia",        "czechia"),
    Country("DNK", "Denmark",        "denmark"),
    Country("EST", "Estonia",        "estonia"),
    Country("FIN", "Finland",        "finland"),
    Country("FRA", "France",         "france"),
    Country("DEU", "Germany",        "germany"),
    Country("GRC", "Greece",         "greece"),
    Country("HUN", "Hungary",        "hungary"),
    Country("IRL", "Ireland",        "ireland"),
    Country("ITA", "Italy",          "italy"),
    Country("LVA", "Latvia",         "latvia"),
    Country("LTU", "Lithuania",      "lithuania"),
    Country("LUX", "Luxembourg",     "luxembourg"),
    Country("MLT", "Malta",          "malta"),
    Country("NLD", "Netherlands",    "netherlands"),
    Country("POL", "Poland",         "poland"),
    Country("PRT", "Portugal",       "portugal"),
    Country("ROU", "Romania",        "romania"),
    Country("SVK", "Slovakia",       "slovakia"),
    Country("SVN", "Slovenia",       "slovenia"),
    Country("ESP", "Spain",          "spain"),
    Country("SWE", "Sweden",         "sweden"),
    # --- Restul Europei (EFTA / Balcani / Est) ---
    Country("ALB", "Albania",        "albania"),
    Country("BIH", "Bosnia and Herzegovina", "bosnia_herzegovina"),
    Country("CHE", "Switzerland",    "switzerland"),
    Country("GBR", "United Kingdom", "united_kingdom"),
    Country("ISL", "Iceland",        "iceland"),
    Country("MDA", "Moldova",        "moldova"),
    Country("MKD", "North Macedonia","north_macedonia"),
    Country("MNE", "Montenegro",     "montenegro"),
    Country("NOR", "Norway",         "norway"),
    Country("SRB", "Serbia",         "serbia"),
    Country("UKR", "Ukraine",        "ukraine"),
    # --- America ---
    Country("USA", "United States",  "united_states"),
    Country("CAN", "Canada",         "canada"),
    Country("MEX", "Mexico",         "mexico"),
    Country("BRA", "Brazil",         "brazil"),
    Country("ARG", "Argentina",      "argentina"),
    Country("CHL", "Chile",          "chile"),
    Country("COL", "Colombia",       "colombia"),
    Country("PER", "Peru",           "peru"),
    # --- Asia ---
    Country("CHN", "China",          "china"),
    Country("IND", "India",          "india"),
    Country("JPN", "Japan",          "japan"),
    Country("KOR", "South Korea",    "south_korea"),
    Country("IDN", "Indonesia",      "indonesia"),
    Country("THA", "Thailand",       "thailand"),
    Country("VNM", "Vietnam",        "vietnam"),
    Country("RUS", "Russia",         "russia"),
    Country("TUR", "Turkey",         "turkey"),
    Country("IRN", "Iran",           "iran"),
    Country("ISR", "Israel",         "israel"),
    Country("SAU", "Saudi Arabia",   "saudi_arabia"),
    # --- Africa ---
    Country("ZAF", "South Africa",   "south_africa"),
    Country("EGY", "Egypt",          "egypt"),
    Country("NGA", "Nigeria",        "nigeria"),
    Country("MAR", "Morocco",        "morocco"),
    # --- Oceania ---
    Country("AUS", "Australia",      "australia"),
    Country("NZL", "New Zealand",    "new_zealand"),
)


def load_country(raw_path, iso3: str) -> pd.DataFrame:
    """Incarca o tara din CSV-ul OWID si o aduce la schema comuna de intrare.

    Pe langa coloanele SIR-centrice (new_cases, total_cases, population),
    incarca si metricile extinse (decese, spitalizari, ATI, vaccinari, teste,
    indici de raspuns) cand exista in CSV — propagate de derive_compartments
    catre output.
    """
    cols = [
        "iso_code", "date", "new_cases", "total_cases", "population",
        # Coloane extinse
        "total_deaths", "new_deaths",
        "hosp_patients", "icu_patients",
        "people_vaccinated", "total_tests",
        "stringency_index", "reproduction_rate",
    ]
    df = pd.read_csv(
        raw_path,
        usecols=lambda c: c in cols,  # accepta lipsa unor coloane (CSV pot diferi)
        parse_dates=["date"],
        dtype={"iso_code": "string"},
    )
    df = df[df["iso_code"] == iso3].copy()
    if df.empty:
        raise ValueError(f"nicio inregistrare pentru iso_code={iso3}")
    df = df[(df["date"] >= START_DATE) & (df["date"] <= END_DATE)]
    df = df.rename(columns={"iso_code": "region"})
    return df.sort_values("date").reset_index(drop=True)


def process_country(raw_path, country: Country) -> None:
    logger.info("[%s] procesez ...", country.iso3)
    raw = load_country(raw_path, country.iso3)
    raw = epi.fill_calendar(raw, START_DATE, END_DATE)
    out = epi.derive_compartments(raw, INFECTIOUS_WINDOW_DAYS)
    epi.validate(out, country.iso3)

    out_path = epi.write_processed(out, country.slug)
    logger.info(
        "[%s] %d randuri -> %s  (I maxim = %d, N = %d)",
        country.iso3, len(out), out_path.relative_to(epi.REPO_ROOT),
        out["infected"].max(), out["population"].iloc[0],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preprocesare OWID COVID-19.")
    parser.add_argument("--force-download", action="store_true",
                        help="re-descarca CSV-ul brut chiar daca exista cache")
    parser.add_argument("--country", action="append", default=None,
                        help="restrange la coduri ISO3 specifice (repetabil)")
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
            logger.error("niciun cod de tara potrivit in %s", wanted)
            return 2

    raw_path = epi.download_if_missing(OWID_URL, RAW_FILE, args.force_download)

    failures: list[str] = []
    for country in targets:
        try:
            process_country(raw_path, country)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] esuat: %s", country.iso3, exc)
            failures.append(country.iso3)

    if failures:
        logger.error("tari esuate: %s", ", ".join(failures))
        return 1

    logger.info("gata. %d tari procesate -> %s", len(targets),
                epi.PROCESSED_DIR.relative_to(epi.REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
