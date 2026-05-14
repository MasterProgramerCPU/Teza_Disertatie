"""Populeaza baza de date cu studii agregate din seturile generate local.

Citeste CSV-urile din ``data/processed/`` (produse de :mod:`preprocess_owid`,
:mod:`preprocess_mpox` si :mod:`generate_synthetic`) si le incarca prin API in
cateva studii agregate, mari:

  * "COVID-19 -- Global"        -- toate tarile OWID COVID-19;
  * "Mpox -- Global 2022-2024"  -- toate tarile OWID mpox;
  * "Benchmark sintetic"        -- seturile sintetice de stres.

Scriptul este idempotent: studiile se identifica dupa nume, iar seturile de
date dupa nume in cadrul studiului, deci o re-rulare nu produce duplicate.
Foloseste ``--dry-run`` pentru a vedea planul fara a scrie nimic.

Exemplu:
    python seed_studies.py --api-url http://localhost:8080 \\
        --email tudor@test.ro --password parola1234 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests

logger = logging.getLogger("seed_studies")

PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"


def covid_files() -> list[Path]:
    return sorted(p for p in PROCESSED_DIR.glob("*.csv")
                  if not p.name.startswith(("mpox_", "synthetic_")))


def mpox_files() -> list[Path]:
    return sorted(PROCESSED_DIR.glob("mpox_*.csv"))


def synthetic_files() -> list[Path]:
    return sorted(PROCESSED_DIR.glob("synthetic_*.csv"))


def dataset_name(path: Path) -> str:
    """Nume lizibil de set de date din numele fisierului."""
    stem = path.stem
    if stem.startswith("mpox_"):
        stem = stem[len("mpox_"):]
    return stem.replace("_", " ").title()


@dataclass
class StudySpec:
    name: str
    disease_code: str
    description: str
    files: list[Path] = field(default_factory=list)


def build_specs() -> list[StudySpec]:
    return [
        StudySpec(
            name="COVID-19 — Global",
            disease_code="covid19",
            description="Serii temporale OWID COVID-19 pentru tari de pe toate "
                        "continentele (Europa, America, Asia, Africa, Oceania), "
                        "2020-2023. Studiu agregat pentru benchmarking pe "
                        "regimuri epidemice variate.",
            files=covid_files(),
        ),
        StudySpec(
            name="Mpox — Global 2022-2024",
            disease_code="mpox",
            description="Serii temporale OWID mpox pentru tarile cu focare "
                        "semnificative, acoperind clada 2022 (Europa/America) si "
                        "clada 2024 (Africa Centrala). A doua boala reala din sistem.",
            files=mpox_files(),
        ),
        StudySpec(
            name="Benchmark sintetic",
            disease_code="synthetic",
            description="Seturi sintetice de stres generate cu un model SIRS cu "
                        "fortare sezoniera (valuri recurente), orizont de 20000 de "
                        "zile. Folosite pentru a impinge limitele sistemului, in "
                        "special antrenarea LSTM si volumul de inserari in baza de date.",
            files=synthetic_files(),
        ),
    ]


class APIError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _data(self, resp: requests.Response):
        """Extrage campul ``data`` din raspuns (dict sau list) sau ridica APIError."""
        try:
            body = resp.json()
        except ValueError:
            raise APIError(f"raspuns non-JSON ({resp.status_code}) de la {resp.url}")
        if resp.status_code >= 400 or (isinstance(body, dict) and "error" in body):
            msg = body.get("error", {}).get("message", resp.text) if isinstance(body, dict) else resp.text
            raise APIError(f"{resp.status_code}: {msg}")
        return body.get("data", {}) if isinstance(body, dict) else body

    def login(self, email: str, password: str) -> None:
        resp = self.session.post(f"{self.base}/api/auth/login",
                                 json={"email": email, "password": password},
                                 timeout=self.timeout)
        token = self._data(resp).get("token")
        if not token:
            raise APIError("login a reusit dar nu a returnat token")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def studies_by_name(self) -> dict[str, str]:
        data = self._data(self.session.get(f"{self.base}/api/studies", timeout=self.timeout))
        return {s["name"]: s["id"] for s in data}

    def create_study(self, name: str, disease_code: str, description: str) -> str:
        resp = self.session.post(f"{self.base}/api/studies",
                                 json={"name": name, "disease_code": disease_code,
                                       "description": description},
                                 timeout=self.timeout)
        return self._data(resp)["id"]

    def dataset_names(self, study_id: str) -> set[str]:
        data = self._data(self.session.get(
            f"{self.base}/api/studies/{study_id}/datasets", timeout=self.timeout))
        return {d["name"] for d in data}

    def upload_dataset(self, study_id: str, name: str, disease_code: str, path: Path) -> None:
        with path.open("rb") as fh:
            resp = self.session.post(
                f"{self.base}/api/studies/{study_id}/datasets",
                data={"name": name, "disease_code": disease_code},
                files={"file": (path.name, fh, "text/csv")},
                timeout=self.timeout,
            )
        self._data(resp)


def seed(client: Client, specs: list[StudySpec], dry_run: bool) -> tuple[int, int]:
    existing = client.studies_by_name()
    created_studies = 0
    uploaded = 0

    for spec in specs:
        if not spec.files:
            logger.warning("[%s] niciun CSV gasit in data/processed/ -- sar", spec.name)
            continue

        if spec.name in existing:
            study_id = existing[spec.name]
            logger.info("[%s] studiu existent, refolosesc (%d CSV-uri de verificat)",
                        spec.name, len(spec.files))
        elif dry_run:
            study_id = ""
            logger.info("[%s] DRY-RUN: as crea studiul + %d seturi de date",
                        spec.name, len(spec.files))
            created_studies += 1
            uploaded += len(spec.files)
            continue
        else:
            study_id = client.create_study(spec.name, spec.disease_code, spec.description)
            logger.info("[%s] studiu creat (%s)", spec.name, study_id)
            created_studies += 1

        present = client.dataset_names(study_id) if study_id else set()
        for path in spec.files:
            name = dataset_name(path)
            if name in present:
                logger.debug("[%s] set '%s' exista deja -- sar", spec.name, name)
                continue
            if dry_run:
                logger.info("[%s] DRY-RUN: as incarca '%s' (%s)", spec.name, name, path.name)
            else:
                client.upload_dataset(study_id, name, spec.disease_code, path)
                logger.info("[%s] incarcat '%s'", spec.name, name)
            uploaded += 1

    return created_studies, uploaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Populeaza baza cu studii agregate.")
    parser.add_argument("--api-url", default="http://localhost:8080",
                        help="URL-ul de baza al API-ului (implicit: http://localhost:8080)")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="arata planul fara a scrie nimic in baza de date")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    specs = build_specs()
    total_files = sum(len(s.files) for s in specs)
    if total_files == 0:
        logger.error("nu exista CSV-uri in %s -- ruleaza intai preprocesarea/generarea",
                     PROCESSED_DIR)
        return 1
    logger.info("plan: %d studii, %d CSV-uri in total", len(specs), total_files)

    client = Client(args.api_url)
    try:
        client.login(args.email, args.password)
    except (APIError, requests.RequestException) as exc:
        logger.error("autentificare esuata: %s", exc)
        return 1

    try:
        created, uploaded = seed(client, specs, args.dry_run)
    except (APIError, requests.RequestException) as exc:
        logger.error("populare esuata: %s", exc)
        return 1

    prefix = "DRY-RUN: " if args.dry_run else ""
    logger.info("%sgata -- %d studii noi, %d seturi de date incarcate",
                prefix, created, uploaded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
