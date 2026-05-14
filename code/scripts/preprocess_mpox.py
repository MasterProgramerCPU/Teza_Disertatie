"""Preprocesare OWID mpox (variola maimutei) -> seturi de date compartimentale.

A doua boala reala din sistem, pe langa COVID-19. Sursa este setul oficial OWID
mpox (date derivate din raportarile OMS pentru focarul mpox inceput in 2022):
https://github.com/owid/monkeypox

Fata de COVID-19, focarul mpox ofera un regim dinamic complet diferit pentru
benchmarking: numar de cazuri cu cateva ordine de marime mai mic raportat la
populatie, doua valuri distincte (clada 2022, predominant in Europa si America,
si clada 2024 din Africa Centrala) si o perioada infectioasa mai lunga.

Particularitati de sursa tratate aici:
  * fisierul mpox nu contine o coloana de populatie; aceasta este derivata din
    raportul total_cases / total_cases_per_million;
  * fereastra infectioasa este de 28 de zile (perioada infectioasa a mpox este
    semnificativ mai lunga decat la COVID-19);
  * tarile sunt selectate automat dupa un prag de cazuri totale, ca seturile sa
    fie suficient de informative.

Derivarea compartimentelor, validarea si scrierea sunt comune cu
:mod:`preprocess_owid` si traiesc in :mod:`epi_common`.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys

import pandas as pd

import epi_common as epi

MPOX_URL = "https://raw.githubusercontent.com/owid/monkeypox/main/owid-monkeypox-data.csv"
START_DATE = pd.Timestamp("2022-05-01")
INFECTIOUS_WINDOW_DAYS = 28
MIN_TOTAL_CASES = 1000

RAW_FILE = epi.RAW_DIR / "owid-monkeypox-data.csv"
ISO3_RE = re.compile(r"^[A-Z]{3}$")

logger = logging.getLogger("preprocess_mpox")


def slugify(location: str) -> str:
    """Transforma numele tarii intr-un slug de fisier (litere mici, _)."""
    slug = re.sub(r"[^a-z0-9]+", "_", location.lower()).strip("_")
    return slug or "region"


def estimate_population(df: pd.DataFrame) -> float:
    """Deduce populatia din total_cases / total_cases_per_million.

    Fisierul mpox nu raporteaza populatia direct. Se foloseste mediana
    raportului peste randurile cu raportare nenula, robusta la variatia mica a
    populatiei de referinta in timp.
    """
    valid = df[(df["total_cases_per_million"] > 0) & (df["total_cases"] > 0)]
    if valid.empty:
        raise ValueError("nu se poate deduce populatia (lipsesc valori per milion)")
    ratio = valid["total_cases"] / valid["total_cases_per_million"] * 1e6
    return float(ratio.median())


def load_country(raw: pd.DataFrame, iso3: str) -> pd.DataFrame:
    """Extrage o tara din CSV-ul mpox si o aduce la schema comuna de intrare."""
    df = raw[raw["iso_code"] == iso3].copy()
    if df.empty:
        raise ValueError(f"nicio inregistrare pentru iso_code={iso3}")
    population = estimate_population(df)
    df = df[df["date"] >= START_DATE]
    df = df.rename(columns={"iso_code": "region"})
    df["population"] = population
    return df[["date", "region", "new_cases", "total_cases", "population"]] \
        .sort_values("date").reset_index(drop=True)


def process_country(raw: pd.DataFrame, iso3: str, slug: str, end_date: pd.Timestamp) -> None:
    logger.info("[%s] procesez ...", iso3)
    df = load_country(raw, iso3)
    df = epi.fill_calendar(df, START_DATE, end_date)
    out = epi.derive_compartments(df, INFECTIOUS_WINDOW_DAYS)
    epi.validate(out, iso3)

    out_path = epi.write_processed(out, f"mpox_{slug}")
    logger.info(
        "[%s] %d randuri -> %s  (I maxim = %d, N = %d)",
        iso3, len(out), out_path.relative_to(epi.REPO_ROOT),
        out["infected"].max(), out["population"].iloc[0],
    )


def select_countries(raw: pd.DataFrame, min_cases: int) -> list[tuple[str, str]]:
    """Tarile cu cel putin ``min_cases`` cazuri totale, ca (iso3, slug)."""
    iso = raw[raw["iso_code"].str.match(ISO3_RE, na=False)]
    last = iso.sort_values("date").groupby("iso_code").tail(1)
    selected = last[last["total_cases"] >= min_cases]
    pairs = [(r.iso_code, slugify(r.location)) for r in selected.itertuples()]
    return sorted(pairs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preprocesare OWID mpox.")
    parser.add_argument("--force-download", action="store_true",
                        help="re-descarca CSV-ul brut chiar daca exista cache")
    parser.add_argument("--country", action="append", default=None,
                        help="restrange la coduri ISO3 specifice (repetabil)")
    parser.add_argument("--min-cases", type=int, default=MIN_TOTAL_CASES,
                        help=f"prag de cazuri totale pentru selectie (implicit {MIN_TOTAL_CASES})")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    raw_path = epi.download_if_missing(MPOX_URL, RAW_FILE, args.force_download)
    raw = pd.read_csv(
        raw_path,
        usecols=["iso_code", "location", "date", "new_cases",
                 "total_cases", "total_cases_per_million"],
        parse_dates=["date"],
        dtype={"iso_code": "string", "location": "string"},
    )
    end_date = raw["date"].max()

    targets = select_countries(raw, args.min_cases)
    if args.country:
        wanted = {c.upper() for c in args.country}
        targets = [(iso, slug) for iso, slug in targets if iso in wanted]
        if not targets:
            logger.error("niciun cod de tara potrivit (peste prag) in %s", wanted)
            return 2

    logger.info("%d tari selectate (>= %d cazuri), fereastra %s -> %s",
                len(targets), args.min_cases, START_DATE.date(), end_date.date())

    failures: list[str] = []
    for iso3, slug in targets:
        try:
            process_country(raw, iso3, slug, end_date)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] esuat: %s", iso3, exc)
            failures.append(iso3)

    if failures:
        logger.error("tari esuate: %s", ", ".join(failures))
        return 1

    logger.info("gata. %d tari mpox procesate -> %s", len(targets),
                epi.PROCESSED_DIR.relative_to(epi.REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
