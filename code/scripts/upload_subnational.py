"""Urcă CSV-urile sub-naționale într-un studiu nou.

Folosește fișierele generate de combine_subnational.py și creează un singur
studiu „COVID-19 — Datasets sub-naționale" cu cele 6 țări mari (USA, Romania,
China, Canada, Australia, France). Fiecare dataset are 9k-60k rânduri.

Exemplu:
    python upload_subnational.py \\
        --api-url http://127.0.0.1:8080 --host-header sir-workbench.ro \\
        --email cercetator@demo.ro --password demo1234parola
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import requests

logger = logging.getLogger("upload_subnational")

ROOT = Path(__file__).resolve().parents[1]
SUBNAT_DIR = ROOT / "data" / "processed" / "subnational"

STUDY_NAME = "COVID-19 — Datasets sub-naționale (10k+ rânduri / țară)"
STUDY_DESC = (
    "Datasets reale cu rezoluție sub-națională: USA pe state-uri (JHU CSSE), "
    "Romania pe județe, China pe provincii, Canada pe provincii/teritorii, "
    "Australia pe state-uri, France pe DOM/TOM (JHU CSSE Global). "
    "Codurile de regiune urmează ISO 3166-2 (ex: US-CA, RO-CJ, CN-HB). "
    "Fiecare dataset are 9.000–60.000 rânduri = (zile × subdiviziuni)."
)

COUNTRIES = [
    ("usa.csv", "USA (50 state-uri + DC)"),
    ("romania.csv", "Romania (42 judete)"),
    ("chn.csv", "China (33 provincii)"),
    ("can.csv", "Canada (13 provincii/teritorii)"),
    ("aus.csv", "Australia (8 state-uri)"),
    ("fra.csv", "France (DOM/TOM)"),
]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", default="http://127.0.0.1:8080")
    p.add_argument("--host-header", default="sir-workbench.ro")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    args = p.parse_args(argv)
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

    session = requests.Session()
    session.headers["Host"] = args.host_header

    # Login
    r = session.post(f"{args.api_url}/api/auth/login",
                     json={"email": args.email, "password": args.password}, timeout=30)
    r.raise_for_status()
    token = r.json()["data"]["token"]
    session.headers["Authorization"] = f"Bearer {token}"

    # Find or create study
    r = session.get(f"{args.api_url}/api/studies", timeout=30)
    studies = {item["study"]["name"]: item["study"]["id"] for item in r.json().get("data") or []}
    if STUDY_NAME in studies:
        sid = studies[STUDY_NAME]
        logger.info("Studiu existent: %s", sid)
    else:
        r = session.post(f"{args.api_url}/api/studies",
                         json={"name": STUDY_NAME, "disease_code": "covid19", "description": STUDY_DESC},
                         timeout=30)
        r.raise_for_status()
        sid = r.json()["data"]["id"]
        logger.info("Studiu creat: %s", sid)

    # List existing datasets to avoid duplicates
    r = session.get(f"{args.api_url}/api/studies/{sid}/datasets", timeout=60)
    existing = {d["name"] for d in r.json().get("data") or []}

    for fname, dataset_name in COUNTRIES:
        path = SUBNAT_DIR / fname
        if not path.exists():
            logger.warning("Lipsește: %s", path)
            continue
        if dataset_name in existing:
            logger.info("Există deja: %s", dataset_name)
            continue
        size_mb = path.stat().st_size / 1e6
        # Numărul de linii (1 minus header)
        with path.open() as fh:
            line_count = sum(1 for _ in fh) - 1
        logger.info("Upload %s (%.1f MB, %d rânduri)...", dataset_name, size_mb, line_count)
        with path.open("rb") as fh:
            r = session.post(
                f"{args.api_url}/api/studies/{sid}/datasets",
                data={"name": dataset_name, "disease_code": "covid19"},
                files={"file": (path.name, fh, "text/csv")},
                timeout=600,
            )
        if r.status_code >= 400:
            logger.error("[%s] eșec %d: %s", dataset_name, r.status_code, r.text[:200])
            continue
        logger.info("  ✔ %s", dataset_name)

    logger.info("Gata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
