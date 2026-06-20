"""Creează studii separate pentru sub-regiunile fiecărei țări, în formatul
„o regiune = un dataset" (necesar ca harta să afișeze culori per-regiune).

Creează:
  - „Demo Hartă — China pe provincii"  (33 datasets)
  - „Demo Hartă — Canada pe provincii" (13 datasets)
  - „Demo Hartă — Australia pe state-uri" (8 datasets)
  - „Demo Hartă — France pe DOM/TOM"   (11 datasets)

Pentru fiecare dataset lansează o simulare SIR/Python cu β derivat
determinist din codul ISO 3166-2 (asigură variație vizibilă pe hartă).

Combinat cu studiile existente:
  - „Demo Hartă — Romania pe județe"        (42 datasets, deja seed-uit)
  - „COVID-19 — USA pe state-uri (JHU CSSE)" (51 datasets, deja sims OK)

avem 6 țări cu hărți sub-naționale funcționale.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
from pathlib import Path

import requests

logger = logging.getLogger("seed_subregions")

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

COUNTRIES = [
    {
        "study_name": "Demo Hartă — China pe provincii",
        "disease_code": "covid19",
        "description": "33 provincii/regiuni administrative ale Chinei, date "
                        "COVID-19 din JHU CSSE Global Province_State. Coduri "
                        "ISO 3166-2 (CN-XX).",
        "csv_dir": PROCESSED / "chn_subdiv",
    },
    {
        "study_name": "Demo Hartă — Canada pe provincii",
        "disease_code": "covid19",
        "description": "13 provincii și teritorii ale Canadei, JHU CSSE Global. "
                        "Coduri ISO 3166-2 (CA-XX).",
        "csv_dir": PROCESSED / "can_subdiv",
    },
    {
        "study_name": "Demo Hartă — Australia pe state-uri",
        "disease_code": "covid19",
        "description": "8 state-uri/teritorii ale Australiei, JHU CSSE Global. "
                        "Coduri ISO 3166-2 (AU-XX).",
        "csv_dir": PROCESSED / "aus_subdiv",
    },
    {
        "study_name": "Demo Hartă — France pe DOM/TOM",
        "disease_code": "covid19",
        "description": "11 departamente și teritorii de peste mări (DOM/TOM) ale "
                        "Franței, JHU CSSE Global. Coduri ISO 3166-2 (FR-XX).",
        "csv_dir": PROCESSED / "fra_subdiv",
    },
]


class APIError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url, host_header=None):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        if host_header:
            self.session.headers["Host"] = host_header

    def _data(self, resp):
        try:
            body = resp.json()
        except ValueError:
            raise APIError(f"non-JSON ({resp.status_code}): {resp.text[:200]}")
        if resp.status_code >= 400 or (isinstance(body, dict) and body.get("error")):
            msg = body.get("error", {}).get("message", resp.text) if isinstance(body, dict) else resp.text
            raise APIError(f"{resp.status_code}: {msg}")
        return body.get("data", {}) if isinstance(body, dict) else body

    def login(self, email, password):
        token = self._data(self.session.post(
            f"{self.base}/api/auth/login",
            json={"email": email, "password": password}, timeout=30,
        )).get("token")
        if not token:
            raise APIError("login fara token")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def studies_by_name(self):
        data = self._data(self.session.get(f"{self.base}/api/studies", timeout=30))
        return {item["study"]["name"]: item["study"]["id"]
                for item in (data or []) if isinstance(item, dict) and item.get("study")}

    def create_study(self, name, disease_code, description):
        return self._data(self.session.post(
            f"{self.base}/api/studies",
            json={"name": name, "disease_code": disease_code, "description": description},
            timeout=30,
        ))["id"]

    def datasets_in_study(self, sid):
        return self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/datasets", timeout=60
        )) or []

    def upload_dataset(self, sid, name, disease, path: Path):
        with path.open("rb") as fh:
            return self._data(self.session.post(
                f"{self.base}/api/studies/{sid}/datasets",
                data={"name": name, "disease_code": disease},
                files={"file": (path.name, fh, "text/csv")},
                timeout=180,
            ))["id"]

    def list_simulations(self, sid):
        return self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/simulations", timeout=60
        )) or []

    def create_simulation(self, sid, dataset, model, lang, t_max, parameters=None):
        payload = {"dataset_id": dataset, "model_type": model,
                   "language": lang, "t_max": t_max}
        if parameters:
            payload["parameters"] = parameters
        return self._data(self.session.post(
            f"{self.base}/api/studies/{sid}/simulations",
            json=payload, timeout=30,
        ))["id"]


def beta_for_region(code: str) -> float:
    """β determinist per regiune (range 0.165..0.45) → R0 ≈ 2.3..6.3 cu γ=1/14."""
    h = int(hashlib.sha256(code.encode()).hexdigest()[:8], 16)
    return round(0.30 * (0.55 + (h % 1000) / 1000.0), 4)


def main(argv=None):
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

    for spec in COUNTRIES:
        csv_dir = spec["csv_dir"]
        csvs = sorted(csv_dir.glob("*.csv")) if csv_dir.exists() else []
        if not csvs:
            logger.warning("[%s] niciun CSV in %s", spec["study_name"], csv_dir)
            continue

        studies = client.studies_by_name()
        if spec["study_name"] in studies:
            sid = studies[spec["study_name"]]
            logger.info("[%s] studiu existent: %s", spec["study_name"], sid)
        else:
            sid = client.create_study(spec["study_name"], spec["disease_code"], spec["description"])
            logger.info("[%s] studiu creat: %s", spec["study_name"], sid)

        present = {d["name"]: d for d in client.datasets_in_study(sid)}
        for path in csvs:
            code = path.stem  # ex "CN-HB"
            if code in present:
                continue
            try:
                client.upload_dataset(sid, code, spec["disease_code"], path)
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] upload %s: %s", spec["study_name"], code, e)
        present = {d["name"]: d for d in client.datasets_in_study(sid)}

        existing = set()
        for s in client.list_simulations(sid):
            if s.get("status") in ("completed", "running", "pending"):
                existing.add((s["dataset_id"], s["model_type"], s["language"]))

        launched = 0
        for path in csvs:
            code = path.stem
            ds = present.get(code)
            if not ds:
                continue
            key = (ds["id"], "sir", "python")
            if key in existing:
                continue
            beta = beta_for_region(code)
            client.create_simulation(sid, ds["id"], "sir", "python", 365,
                                     parameters={"beta": beta, "gamma": 0.0714})
            launched += 1
            time.sleep(0.05)
        logger.info("[%s] %d simulări lansate", spec["study_name"], launched)

    logger.info("Gata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
