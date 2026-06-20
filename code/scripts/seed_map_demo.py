"""Seed dedicat pentru demo-ul de hartă.

Creează două studii prin API si lansează simulări pentru fiecare:

  1. "Demo Hartă — COVID-19 64 țări":
     - upload pentru toate CSV-urile COVID din data/processed/
     - simulare SIR/Python și SIDARTHE/Python pentru fiecare țară (t_max=365)

  2. "Demo Hartă — Romania focus":
     - un singur dataset (Romania)
     - simulare SIR/Python (t_max=365)
     - demonstrează zoom-ul automat al hărții cand studiul are o singură țară

Scriptul e idempotent: re-rulările sar peste studii / dataset-uri / simulări
existente.

Exemplu:
    python seed_map_demo.py --api-url http://127.0.0.1:8080 \\
        --email cercetator@demo.ro --password demo1234parola
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

logger = logging.getLogger("seed_map_demo")

PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"

POLL_INTERVAL_SEC = 1.0
POLL_TIMEOUT_SEC = 180.0


@dataclass
class StudySpec:
    name: str
    disease_code: str
    description: str
    csv_files: list[Path]
    models: list[str]   # ex: ["sir", "sidarthe"]
    language: str = "python"
    t_max: int = 365


class APIError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url: str, host_header: str | None = None, timeout: float = 60.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        if host_header:
            self.session.headers["Host"] = host_header

    def _data(self, resp: requests.Response):
        try:
            body = resp.json()
        except ValueError:
            raise APIError(f"raspuns non-JSON ({resp.status_code}) de la {resp.url}: {resp.text[:200]}")
        if resp.status_code >= 400 or (isinstance(body, dict) and body.get("error")):
            msg = body.get("error", {}).get("message", resp.text) if isinstance(body, dict) else resp.text
            raise APIError(f"{resp.status_code} {resp.url}: {msg}")
        return body.get("data", {}) if isinstance(body, dict) else body

    def login(self, email: str, password: str) -> None:
        resp = self.session.post(
            f"{self.base}/api/auth/login",
            json={"email": email, "password": password},
            timeout=self.timeout,
        )
        token = self._data(resp).get("token")
        if not token:
            raise APIError("login a reusit dar nu a returnat token")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def studies_by_name(self) -> dict[str, str]:
        # /api/studies returnează list[{study, role}], nu list[Study]
        data = self._data(self.session.get(f"{self.base}/api/studies", timeout=self.timeout))
        out: dict[str, str] = {}
        for item in data or []:
            s = item.get("study") if isinstance(item, dict) else None
            if s and "name" in s and "id" in s:
                out[s["name"]] = s["id"]
        return out

    def create_study(self, name: str, disease_code: str, description: str) -> str:
        resp = self.session.post(
            f"{self.base}/api/studies",
            json={"name": name, "disease_code": disease_code, "description": description},
            timeout=self.timeout,
        )
        return self._data(resp)["id"]

    def datasets_in_study(self, study_id: str) -> list[dict]:
        return self._data(self.session.get(
            f"{self.base}/api/studies/{study_id}/datasets", timeout=self.timeout
        )) or []

    def upload_dataset(self, study_id: str, name: str, disease_code: str, path: Path) -> str:
        with path.open("rb") as fh:
            resp = self.session.post(
                f"{self.base}/api/studies/{study_id}/datasets",
                data={"name": name, "disease_code": disease_code},
                files={"file": (path.name, fh, "text/csv")},
                timeout=self.timeout * 3,
            )
        return self._data(resp)["id"]

    def list_simulations(self, study_id: str) -> list[dict]:
        return self._data(self.session.get(
            f"{self.base}/api/studies/{study_id}/simulations", timeout=self.timeout
        )) or []

    def create_simulation(self, study_id: str, dataset_id: str,
                          model: str, language: str, t_max: int) -> str:
        resp = self.session.post(
            f"{self.base}/api/studies/{study_id}/simulations",
            json={
                "dataset_id": dataset_id,
                "model_type": model,
                "language": language,
                "t_max": t_max,
            },
            timeout=self.timeout,
        )
        return self._data(resp)["id"]

    def simulation_status(self, study_id: str, sim_id: str) -> str:
        d = self._data(self.session.get(
            f"{self.base}/api/studies/{study_id}/simulations/{sim_id}",
            timeout=self.timeout,
        ))
        return d.get("status", "unknown")


def dataset_name_for(path: Path) -> str:
    return path.stem.replace("_", " ").title()


def covid_files() -> list[Path]:
    """Toate CSV-urile COVID (exclude mpox + sintetice)."""
    return sorted(
        p for p in PROCESSED_DIR.glob("*.csv")
        if not p.name.startswith(("mpox_", "synthetic_"))
    )


def build_specs(country_filter: list[str] | None = None) -> list[StudySpec]:
    covid = covid_files()
    if country_filter:
        names = {c.lower() for c in country_filter}
        covid = [p for p in covid if p.stem.lower() in names]

    romania = [p for p in covid_files() if p.stem == "romania"]

    return [
        StudySpec(
            name="Demo Hartă — COVID-19 selecție globală",
            disease_code="covid19",
            description=(
                "Studiu de demonstrație pentru pagina hartă. Conține datele OWID "
                "COVID-19 pentru toate țările preprocesate (selectate să acopere "
                "Europa, America, Asia, Africa și Oceania). Pentru fiecare țară s-au "
                "lansat automat două simulări: SIR și SIDARTHE, ambele în Python, "
                "orizont 365 zile."
            ),
            csv_files=covid,
            models=["sir", "sidarthe"],
        ),
        StudySpec(
            name="Demo Hartă — Romania focus",
            disease_code="covid19",
            description=(
                "Studiu de demonstrație pentru zoom-ul automat al hărții pe o "
                "singură țară. Conține un singur dataset (Romania OWID) și o "
                "simulare SIR/Python (orizont 365 zile)."
            ),
            csv_files=romania,
            models=["sir"],
        ),
    ]


def wait_for_sim(client: Client, study_id: str, sim_id: str, label: str) -> str:
    """Așteaptă finalizarea unei simulări. Returnează statusul final."""
    t0 = time.time()
    last_status = "pending"
    while time.time() - t0 < POLL_TIMEOUT_SEC:
        st = client.simulation_status(study_id, sim_id)
        if st in ("completed", "failed"):
            return st
        if st != last_status:
            logger.debug("[%s] %s", label, st)
            last_status = st
        time.sleep(POLL_INTERVAL_SEC)
    logger.warning("[%s] timeout după %.0fs (ultim status: %s)", label, POLL_TIMEOUT_SEC, last_status)
    return last_status


def seed_one(client: Client, spec: StudySpec) -> None:
    studies = client.studies_by_name()
    if spec.name in studies:
        study_id = studies[spec.name]
        logger.info("[%s] studiu existent (%s)", spec.name, study_id)
    else:
        study_id = client.create_study(spec.name, spec.disease_code, spec.description)
        logger.info("[%s] studiu creat (%s)", spec.name, study_id)

    if not spec.csv_files:
        logger.warning("[%s] niciun CSV — sar peste upload", spec.name)
        return

    # Upload (idempotent prin nume)
    present = {d["name"]: d for d in client.datasets_in_study(study_id)}
    for path in spec.csv_files:
        ds_name = dataset_name_for(path)
        if ds_name in present:
            logger.debug("[%s] '%s' există deja", spec.name, ds_name)
            continue
        client.upload_dataset(study_id, ds_name, spec.disease_code, path)
        logger.info("[%s] upload '%s'", spec.name, ds_name)

    # Refresh lista
    present = {d["name"]: d for d in client.datasets_in_study(study_id)}

    # Inventar simulări existente pentru a sări peste duplicate
    existing = client.list_simulations(study_id)
    have = set()
    for s in existing:
        if s.get("status") in ("completed", "running", "pending"):
            have.add((s["dataset_id"], s["model_type"], s["language"]))

    # Lansăm simulările lipsă pentru fiecare model
    launched: list[tuple[str, str, str, str]] = []  # (label, study, sim_id, status_so_far)
    for path in spec.csv_files:
        ds_name = dataset_name_for(path)
        ds = present.get(ds_name)
        if not ds:
            continue
        for model in spec.models:
            key = (ds["id"], model, spec.language)
            if key in have:
                logger.debug("[%s] sim %s/%s/%s există", spec.name, ds_name, model, spec.language)
                continue
            label = f"{ds_name}/{model}/{spec.language}"
            sim_id = client.create_simulation(study_id, ds["id"], model, spec.language, spec.t_max)
            logger.info("[%s] lansat %s (sim=%s)", spec.name, label, sim_id)
            launched.append((label, study_id, sim_id, "pending"))

    # Așteaptă rezultatul tuturor (paralelism asincron pe runner-e)
    for i, (label, sid, sim_id, _) in enumerate(launched, 1):
        st = wait_for_sim(client, sid, sim_id, label)
        marker = "✔" if st == "completed" else "✘"
        logger.info("[%s] %s %s (%d/%d)", spec.name, marker, label, i, len(launched))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed dedicat demo-ului de hartă")
    parser.add_argument("--api-url", default="http://127.0.0.1:8080")
    parser.add_argument("--host-header", default="sir-workbench.ro",
                        help="header Host când API-ul e accesat prin port-forward (default: sir-workbench.ro)")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    client = Client(args.api_url, host_header=args.host_header)
    try:
        client.login(args.email, args.password)
    except (APIError, requests.RequestException) as exc:
        logger.error("autentificare eșuată: %s", exc)
        return 1

    for spec in build_specs():
        try:
            seed_one(client, spec)
        except (APIError, requests.RequestException) as exc:
            logger.error("[%s] eșec: %s", spec.name, exc)
            return 1

    logger.info("demo seed completat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
