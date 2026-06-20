"""Campanie de simulări pentru a depăși 10k entry-uri în simulation_runs.

Pentru fiecare studiu accesibil utilizatorului curent, lansează simulări pentru
fiecare combinație (dataset × model × limbaj) configurată, sărind peste cele
deja prezente cu status completed/running/pending.

Strategie:
  - 5 modele compartimentale (SIR, SIS, SEIR, SIRS, SIDARTHE) × 3 limbaje (R,
    Julia, Python) × t_max = 365 zile — combinație de bază
  - Fire-and-forget: trimitem POST /simulations, lăsăm runner-ele să le proceseze
    asincron. La final raportăm câte am lansat.
  - Idempotent: sare peste rulările care deja există pentru aceeași combinație.

Sursa numerelor:
  • Modelele: implementate în runner-ele R/Julia/Python descrise în cap. 5 al
    tezei.
  • Datasets: din studiile reale (OWID COVID-19, OWID mpox, JHU CSSE US states,
    Romania pe județe).
  • Parametrii implicit: β=0.3, γ=1/14 (standard COVID-19 din literatura
    clinică); pentru SIDARTHE setul din Giordano et al. 2020.

Exemplu:
    python seed_simulation_campaign.py \\
        --api-url http://127.0.0.1:8080 --host-header sir-workbench.ro \\
        --email cercetator@demo.ro --password demo1234parola \\
        --max-launches 12000
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import requests

logger = logging.getLogger("sim_campaign")

# Combinatii (model, limbaj) lansate per dataset. Ordonate pentru a alterna
# limbajele si a distribui sarcina uniform pe runner-ele R/Julia/Python.
COMBINATIONS: list[tuple[str, str, int]] = [
    # (model, limbaj, t_max)
    ("sir",      "python", 365),
    ("sir",      "julia",  365),
    ("sir",      "r",      365),
    ("sis",      "python", 365),
    ("sis",      "julia",  365),
    ("sis",      "r",      365),
    ("seir",     "python", 365),
    ("seir",    "julia",   365),
    ("seir",     "r",      365),
    ("sirs",     "python", 365),
    ("sirs",     "julia",  365),
    ("sirs",     "r",      365),
    ("sidarthe", "python", 365),
    ("sidarthe", "julia",  365),
    ("sidarthe", "r",      365),
    # Adițional t_max=90 doar pe python pentru variație
    ("sir",      "python", 90),
    ("sidarthe", "python", 90),
    ("seir",     "python", 90),
    ("sirs",     "python", 90),
    ("sis",      "python", 90),
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

    def my_studies(self) -> list[dict]:
        """Returnează list de Study cu rol admin/researcher (pot lansa simulări)."""
        data = self._data(self.session.get(f"{self.base}/api/studies", timeout=30))
        out = []
        for item in data or []:
            if not isinstance(item, dict):
                continue
            role = item.get("role", "")
            s = item.get("study")
            if s and role in ("admin", "researcher"):
                out.append(s)
        return out

    def datasets_in_study(self, sid: str) -> list[dict]:
        return self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/datasets", timeout=60
        )) or []

    def existing_sims(self, sid: str) -> set[tuple[str, str, str, int]]:
        """(dataset_id, model, language, t_max) → ignorăm dacă există completat/running/pending."""
        sims = self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/simulations", timeout=60
        )) or []
        out = set()
        for s in sims:
            if s.get("status") in ("completed", "running", "pending"):
                out.add((s["dataset_id"], s["model_type"], s["language"], int(s.get("t_max", 0))))
        return out

    def create_simulation(self, sid: str, dataset: str, model: str, lang: str, t_max: int) -> str:
        resp = self.session.post(
            f"{self.base}/api/studies/{sid}/simulations",
            json={"dataset_id": dataset, "model_type": model, "language": lang, "t_max": t_max},
            timeout=30,
        )
        return self._data(resp)["id"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", default="http://127.0.0.1:8080")
    p.add_argument("--host-header", default="sir-workbench.ro")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--max-launches", type=int, default=15000,
                   help="Plafon de simulări de lansat (default: 15000)")
    p.add_argument("--launch-delay-ms", type=int, default=20,
                   help="Pauză între cereri ca să nu îneci API-ul (default: 20ms)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

    client = Client(args.api_url, host_header=args.host_header)
    try:
        client.login(args.email, args.password)
    except Exception as e:  # noqa: BLE001
        logger.error("login: %s", e)
        return 1

    studies = client.my_studies()
    logger.info("Studii accesibile (admin/researcher): %d", len(studies))

    total_planned = 0
    total_skipped_existing = 0
    total_launched = 0
    total_failed = 0

    delay_s = args.launch_delay_ms / 1000.0

    for st in studies:
        sid = st["id"]
        name = st["name"]
        try:
            datasets = client.datasets_in_study(sid)
            existing = client.existing_sims(sid)
        except Exception as e:  # noqa: BLE001
            logger.warning("[%s] eșec listare: %s", name, e)
            continue

        if not datasets:
            continue
        logger.info("[%s] %d dataset-uri, %d sims existente",
                    name, len(datasets), len(existing))

        for ds in datasets:
            if total_launched >= args.max_launches:
                break
            for model, lang, t_max in COMBINATIONS:
                key = (ds["id"], model, lang, t_max)
                if key in existing:
                    total_skipped_existing += 1
                    continue
                total_planned += 1
                if total_launched >= args.max_launches:
                    break
                if args.dry_run:
                    continue
                try:
                    client.create_simulation(sid, ds["id"], model, lang, t_max)
                    total_launched += 1
                    if total_launched % 200 == 0:
                        logger.info("  lansat %d / plafon %d (skipped existing %d, failed %d)",
                                    total_launched, args.max_launches,
                                    total_skipped_existing, total_failed)
                except Exception as e:  # noqa: BLE001
                    total_failed += 1
                    if total_failed < 10:
                        logger.warning("  fail %s/%s/%s: %s", ds["name"], model, lang, e)
                time.sleep(delay_s)
        if total_launched >= args.max_launches:
            logger.info("Plafon atins (%d). Opresc.", args.max_launches)
            break

    logger.info(
        "Gata: %d planificate, %d sărite (există), %d lansate, %d eșuate.%s",
        total_planned, total_skipped_existing, total_launched, total_failed,
        " (DRY RUN — nimic lansat)" if args.dry_run else "",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
