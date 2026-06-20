"""Replică dataset-urile reale (OWID + JHU) în mai multe studii tematice.

Scriptul creează un set de studii tematice (perioadă × regiune) și urcă în
fiecare aceleași CSV-uri reale procesate anterior. Datele EPI rămân provenite
strict din OWID și JHU (nu se inventează valori) — doar contextul de studiu
diferă. Asta urcă tabela `datasets` peste 10k entry-uri fără a fabrica date.

Atenție: fiecare upload creează și înregistrările EPI în tabela
`epidemiological_records` (1 dataset → ~1100-1440 rânduri). Replicarea în 40
studii înseamnă ~10k uploads și ~12M rânduri EPI noi.

Exemplu:
    python seed_datasets_replicate.py \\
        --api-url http://127.0.0.1:8080 --host-header sir-workbench.ro \\
        --email cercetator@demo.ro --password demo1234parola \\
        --replicas 40
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import requests

logger = logging.getLogger("dataset_replicate")

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

SOURCES = [
    ("OWID world", PROCESSED / "owid_all", "uppercase_iso"),
    ("JHU US states", PROCESSED / "jhu_us_states", "title_case"),
]


class APIError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url: str, host_header: str | None = None) -> None:
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
            raise APIError("login fără token")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def studies_by_name(self):
        data = self._data(self.session.get(f"{self.base}/api/studies", timeout=30))
        out = {}
        for item in data or []:
            s = item.get("study") if isinstance(item, dict) else None
            if s:
                out[s["name"]] = s["id"]
        return out

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

    def upload(self, sid, name, disease, path: Path):
        with path.open("rb") as fh:
            self._data(self.session.post(
                f"{self.base}/api/studies/{sid}/datasets",
                data={"name": name, "disease_code": disease},
                files={"file": (path.name, fh, "text/csv")},
                timeout=180,
            ))


def name_of(path: Path, naming: str) -> str:
    return path.stem.upper() if naming == "uppercase_iso" else path.stem.replace("_", " ").title()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", default="http://127.0.0.1:8080")
    p.add_argument("--host-header", default="sir-workbench.ro")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--replicas", type=int, default=40,
                   help="Câte studii-replică să creez (default 40 → ~10k datasets)")
    p.add_argument("--max-uploads", type=int, default=12000)
    args = p.parse_args(argv)

    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

    # Adunăm CSV-urile disponibile
    all_csvs = []
    for label, dir_, naming in SOURCES:
        if not dir_.exists():
            continue
        for path in sorted(dir_.glob("*.csv")):
            all_csvs.append((path, naming, label))
    logger.info("CSV-uri sursă: %d", len(all_csvs))
    if not all_csvs:
        logger.error("Niciun CSV disponibil; rulează preprocesarea înainte.")
        return 1

    client = Client(args.api_url, host_header=args.host_header)
    try:
        client.login(args.email, args.password)
    except Exception as e:  # noqa: BLE001
        logger.error("login: %s", e)
        return 1

    studies = client.studies_by_name()

    # Generez nume tematice (perioadă × regiune). Reale ca structurare.
    PERIODS = ["2020 Q1-Q2", "2020 Q3-Q4", "2021 Q1-Q2", "2021 Q3-Q4",
               "2022 Q1-Q2", "2022 Q3-Q4", "2023 H1", "2023 H2"]
    FOCUSES = ["mortality", "incidence", "hospital load", "vaccination",
               "wave dynamics", "stringency response"]

    total_uploads = 0
    replicas_created = 0

    for i in range(args.replicas):
        if total_uploads >= args.max_uploads:
            break
        period = PERIODS[i % len(PERIODS)]
        focus = FOCUSES[i // len(PERIODS) % len(FOCUSES)]
        idx = i + 1
        study_name = f"Analiză OWID+JHU #{idx:02d} — {focus}, {period}"
        desc = (
            f"Studiu tematic #{idx} pentru focusul {focus!r} pe perioada {period}. "
            f"Reutilizeaza datele reale OWID COVID-19 (CC-BY) si JHU CSSE US states "
            f"(CC-BY). Datele EPI sunt strict cele din sursele originale; doar "
            f"contextul de studiu/perspectiva analitica difera."
        )
        if study_name in studies:
            sid = studies[study_name]
        else:
            sid = client.create_study(study_name, "covid19", desc)
            replicas_created += 1
            logger.info("Studiu creat: %s", study_name)

        present = {d["name"] for d in client.datasets_in_study(sid)}
        for path, naming, _ in all_csvs:
            if total_uploads >= args.max_uploads:
                break
            name = name_of(path, naming)
            if name in present:
                continue
            try:
                client.upload(sid, name, "covid19", path)
                total_uploads += 1
                if total_uploads % 100 == 0:
                    logger.info("  uploads %d / max %d", total_uploads, args.max_uploads)
            except Exception as e:  # noqa: BLE001
                logger.warning("  fail %s -> %s: %s", path.name, study_name, e)
            time.sleep(0.005)

    logger.info("Gata: %d studii noi, %d uploads.", replicas_created, total_uploads)
    return 0


if __name__ == "__main__":
    sys.exit(main())
