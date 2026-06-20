"""Seed pentru studiile cu date extinse (OWID complet + JHU CSSE US states).

Creează două studii noi:

  1. „COVID-19 — World OWID complet (2020-2024)":
     toate cele ~205 țări cu date OWID suficiente, ISO3 ca region_code.
     CSV-uri în data/processed/owid_all/.

  2. „COVID-19 — USA pe state-uri (JHU CSSE)":
     50 state-uri SUA + DC, cu date JHU CSSE daily.
     CSV-uri în data/processed/jhu_us_states/.

Idempotent: re-rulările sar peste dataset-urile care există deja.

Exemplu:
    python seed_extended_data.py \
        --api-url http://127.0.0.1:8080 --host-header sir-workbench.ro \
        --email cercetator@demo.ro --password demo1234parola
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import requests

logger = logging.getLogger("seed_extended")

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


@dataclass
class StudySpec:
    name: str
    disease_code: str
    description: str
    csv_dir: Path
    naming: str  # "uppercase_iso" sau "title_case"


SPECS: list[StudySpec] = [
    StudySpec(
        name="COVID-19 — World OWID complet (2020-2024)",
        disease_code="covid19",
        description=(
            "Toate țările cu date OWID COVID-19 suficiente (≥100 zile cu raportare "
            "nenulă). ~205 dataset-uri ISO3 din sursa Our World in Data, distribuit "
            "sub CC-BY 4.0. Acoperire temporală: 22 ian. 2020 — 31 dec. 2023."
        ),
        csv_dir=PROCESSED / "owid_all",
        naming="uppercase_iso",
    ),
    StudySpec(
        name="COVID-19 — USA pe state-uri (JHU CSSE)",
        disease_code="covid19",
        description=(
            "50 state-uri SUA + Districtul Columbia, date COVID-19 daily de la "
            "Johns Hopkins University CSSE. Sursa: github.com/CSSEGISandData/COVID-19 "
            "(CC-BY 4.0). Acoperire: 22 ian. 2020 — 9 mar. 2023 (ultima actualizare JHU)."
        ),
        csv_dir=PROCESSED / "jhu_us_states",
        naming="title_case",
    ),
]


class APIError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url: str, host_header: str | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        if host_header:
            self.session.headers["Host"] = host_header

    def _data(self, resp: requests.Response):
        try:
            body = resp.json()
        except ValueError:
            raise APIError(f"non-JSON ({resp.status_code}): {resp.text[:200]}")
        if resp.status_code >= 400 or (isinstance(body, dict) and body.get("error")):
            msg = body.get("error", {}).get("message", resp.text) if isinstance(body, dict) else resp.text
            raise APIError(f"{resp.status_code}: {msg}")
        return body.get("data", {}) if isinstance(body, dict) else body

    def login(self, email: str, password: str) -> None:
        resp = self.session.post(
            f"{self.base}/api/auth/login",
            json={"email": email, "password": password}, timeout=30,
        )
        token = self._data(resp).get("token")
        if not token:
            raise APIError("login fără token")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def studies_by_name(self) -> dict[str, str]:
        data = self._data(self.session.get(f"{self.base}/api/studies", timeout=30))
        out = {}
        for item in data or []:
            s = item.get("study") if isinstance(item, dict) else None
            if s:
                out[s["name"]] = s["id"]
        return out

    def create_study(self, name: str, disease_code: str, description: str) -> str:
        resp = self.session.post(
            f"{self.base}/api/studies",
            json={"name": name, "disease_code": disease_code, "description": description},
            timeout=30,
        )
        return self._data(resp)["id"]

    def datasets_in_study(self, sid: str) -> list[dict]:
        return self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/datasets", timeout=60
        )) or []

    def upload_dataset(self, sid: str, name: str, disease: str, path: Path) -> str:
        with path.open("rb") as fh:
            resp = self.session.post(
                f"{self.base}/api/studies/{sid}/datasets",
                data={"name": name, "disease_code": disease},
                files={"file": (path.name, fh, "text/csv")},
                timeout=180,
            )
        return self._data(resp)["id"]


def dataset_name_for(path: Path, naming: str) -> str:
    stem = path.stem
    if naming == "uppercase_iso":
        return stem.upper()  # "rou" -> "ROU"
    # title_case
    return stem.replace("_", " ").title()


def seed_one(client: Client, spec: StudySpec) -> None:
    if not spec.csv_dir.exists():
        logger.warning("Director lipsă: %s", spec.csv_dir)
        return
    csvs = sorted(spec.csv_dir.glob("*.csv"))
    if not csvs:
        logger.warning("[%s] niciun CSV în %s", spec.name, spec.csv_dir)
        return

    studies = client.studies_by_name()
    if spec.name in studies:
        sid = studies[spec.name]
        logger.info("[%s] studiu existent: %s", spec.name, sid)
    else:
        sid = client.create_study(spec.name, spec.disease_code, spec.description)
        logger.info("[%s] studiu creat: %s", spec.name, sid)

    present = {d["name"]: d for d in client.datasets_in_study(sid)}
    uploaded = 0
    for path in csvs:
        name = dataset_name_for(path, spec.naming)
        if name in present:
            continue
        try:
            client.upload_dataset(sid, name, spec.disease_code, path)
            uploaded += 1
            if uploaded % 25 == 0:
                logger.info("[%s] uploaded %d/%d", spec.name, uploaded, len(csvs))
        except Exception as e:  # noqa: BLE001
            logger.warning("[%s] eșec %s: %s", spec.name, path.name, e)
    logger.info("[%s] gata: %d dataset-uri noi încărcate", spec.name, uploaded)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", default="http://127.0.0.1:8080")
    p.add_argument("--host-header", default="sir-workbench.ro")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    args = p.parse_args(argv)

    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

    client = Client(args.api_url, host_header=args.host_header)
    try:
        client.login(args.email, args.password)
    except Exception as e:  # noqa: BLE001
        logger.error("login: %s", e)
        return 1

    for spec in SPECS:
        try:
            seed_one(client, spec)
        except Exception as e:  # noqa: BLE001
            logger.error("[%s] eșec: %s", spec.name, e)

    logger.info("Seed extins complet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
