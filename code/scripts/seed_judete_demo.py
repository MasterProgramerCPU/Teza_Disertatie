"""Seed pentru studiul demo „Romania pe județe".

Creează un studiu nou și încarcă cele 42 CSV-uri din
data/processed/ro_judete/, apoi lansează o simulare SIR/Python (t_max=365)
pentru fiecare județ.

Pentru ca harta să fie vizibil eterogenă (nu toate județele să atingă același
peak SIR), β e variat per județ după un factor determinist derivat din codul
mnemonic (același mecanism ca în generate_romania_counties.py). γ rămâne fix la
1/14 zile (referință COVID-19). Acest design produce R₀ în [2.3, 6.3], deci
peak-uri și calendare semnificativ diferite — exact ce avem nevoie pentru demo.

Idempotent: re-rulările sar peste ce există deja. Pentru a forța rulări noi
folosește --force-relaunch (lansează simulări noi chiar dacă există rulări
completate; cea mai recentă va fi cea afișată pe hartă).

Exemplu:
    python seed_judete_demo.py \
        --api-url http://127.0.0.1:8080 --host-header sir-workbench.ro \
        --email cercetator@demo.ro --password demo1234parola
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
from pathlib import Path

import requests

logger = logging.getLogger("seed_judete")

ROOT = Path(__file__).resolve().parents[1]
JUDETE_DIR = ROOT / "data" / "processed" / "ro_judete"

POLL_INTERVAL_SEC = 1.0
POLL_TIMEOUT_SEC = 120.0

STUDY_NAME = "Demo Hartă — Romania pe județe"
STUDY_DESC = (
    "Studiu de demonstrație pentru harta României la nivel de județ. "
    "Date sintetice distribuite din seria națională OWID pe baza populației "
    "din 2011, cu un factor multiplicativ per județ pentru a face hărțile "
    "vizibil eterogene. 42 dataset-uri (câte unul per județ, cu region=RO-XX), "
    "simulări SIR/Python orizont 365 zile pentru fiecare."
)


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
            raise APIError(f"non-JSON ({resp.status_code}): {resp.text[:200]}")
        if resp.status_code >= 400 or (isinstance(body, dict) and body.get("error")):
            msg = body.get("error", {}).get("message", resp.text) if isinstance(body, dict) else resp.text
            raise APIError(f"{resp.status_code}: {msg}")
        return body.get("data", {}) if isinstance(body, dict) else body

    def login(self, email: str, password: str) -> None:
        resp = self.session.post(f"{self.base}/api/auth/login",
                                 json={"email": email, "password": password},
                                 timeout=self.timeout)
        token = self._data(resp).get("token")
        if not token:
            raise APIError("login fără token")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def studies_by_name(self) -> dict[str, str]:
        data = self._data(self.session.get(f"{self.base}/api/studies", timeout=self.timeout))
        out = {}
        for item in data or []:
            s = item.get("study") if isinstance(item, dict) else None
            if s:
                out[s["name"]] = s["id"]
        return out

    def create_study(self, name: str, disease_code: str, description: str) -> str:
        resp = self.session.post(f"{self.base}/api/studies",
                                 json={"name": name, "disease_code": disease_code,
                                       "description": description}, timeout=self.timeout)
        return self._data(resp)["id"]

    def datasets_in_study(self, sid: str) -> list[dict]:
        return self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/datasets", timeout=self.timeout
        )) or []

    def upload_dataset(self, sid: str, name: str, disease: str, path: Path) -> str:
        with path.open("rb") as fh:
            resp = self.session.post(
                f"{self.base}/api/studies/{sid}/datasets",
                data={"name": name, "disease_code": disease},
                files={"file": (path.name, fh, "text/csv")},
                timeout=self.timeout * 3,
            )
        return self._data(resp)["id"]

    def list_simulations(self, sid: str) -> list[dict]:
        return self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/simulations", timeout=self.timeout
        )) or []

    def create_simulation(
        self,
        sid: str,
        dataset: str,
        model: str,
        lang: str,
        t_max: int,
        parameters: dict | None = None,
    ) -> str:
        payload: dict = {"dataset_id": dataset, "model_type": model, "language": lang, "t_max": t_max}
        if parameters:
            payload["parameters"] = parameters
        resp = self.session.post(
            f"{self.base}/api/studies/{sid}/simulations",
            json=payload,
            timeout=self.timeout,
        )
        return self._data(resp)["id"]

    def sim_status(self, sid: str, sim_id: str) -> str:
        d = self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/simulations/{sim_id}", timeout=self.timeout
        ))
        return d.get("status", "unknown")


def wait_for(client: Client, sid: str, sim_id: str) -> str:
    t0 = time.time()
    while time.time() - t0 < POLL_TIMEOUT_SEC:
        st = client.sim_status(sid, sim_id)
        if st in ("completed", "failed"):
            return st
        time.sleep(POLL_INTERVAL_SEC)
    return "timeout"


def beta_for_county(code: str) -> float:
    """β specific per județ în [0.165, 0.45].

    Deterministic pe baza codului ISO 3166-2 (RO-XX). Cu γ = 1/14, asta produce
    R₀ în [2.3, 6.3], adică peak SIR și calendar semnificativ diferite între
    județe — exact ce face harta vizibil eterogenă.
    """
    h = int(hashlib.sha256(code.encode()).hexdigest()[:8], 16)
    factor = 0.55 + (h % 1000) / 1000.0  # 0.55..1.55
    return round(0.30 * factor, 4)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", default="http://127.0.0.1:8080")
    p.add_argument("--host-header", default="sir-workbench.ro")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument(
        "--force-relaunch",
        action="store_true",
        help="Lansează simulări noi chiar dacă există deja rulări completate "
             "(cea mai recentă va fi cea afișată pe hartă).",
    )
    args = p.parse_args(argv)

    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

    csv_files = sorted(JUDETE_DIR.glob("RO-*.csv"))
    if not csv_files:
        logger.error("Niciun CSV în %s; rulează generate_romania_counties.py", JUDETE_DIR)
        return 1
    logger.info("Plan: %d județe", len(csv_files))

    client = Client(args.api_url, host_header=args.host_header)
    try:
        client.login(args.email, args.password)
    except Exception as e:
        logger.error("login: %s", e)
        return 1

    studies = client.studies_by_name()
    if STUDY_NAME in studies:
        sid = studies[STUDY_NAME]
        logger.info("Studiu existent: %s", sid)
    else:
        sid = client.create_study(STUDY_NAME, "covid19", STUDY_DESC)
        logger.info("Studiu creat: %s", sid)

    # Upload (idempotent prin nume)
    existing = {d["name"]: d for d in client.datasets_in_study(sid)}
    for path in csv_files:
        # Numele = "RO-XX (NumeJudeț)" — extragem doar codul
        code = path.stem  # RO-XX
        name = code
        if name in existing:
            continue
        client.upload_dataset(sid, name, "covid19", path)
        logger.info("Upload %s", name)
        existing = {d["name"]: d for d in client.datasets_in_study(sid)}

    # Lansare simulări — β per județ, γ fix la 1/14 (≈ 0.0714)
    existing = {d["name"]: d for d in client.datasets_in_study(sid)}
    sims = client.list_simulations(sid)
    have = set((s["dataset_id"], s["model_type"], s["language"])
               for s in sims if s["status"] in ("completed", "running", "pending"))

    launched = []
    for path in csv_files:
        code = path.stem
        ds = existing.get(code)
        if not ds:
            continue
        key = (ds["id"], "sir", "python")
        if key in have and not args.force_relaunch:
            continue
        beta = beta_for_county(code)
        gamma = 0.0714
        params = {"beta": beta, "gamma": gamma}
        sim_id = client.create_simulation(sid, ds["id"], "sir", "python", 365, parameters=params)
        launched.append((code, sim_id))
        logger.info("Lansat %s β=%.4f γ=%.4f R0=%.2f (sim=%s)",
                    code, beta, gamma, beta / gamma, sim_id)

    for i, (code, sim_id) in enumerate(launched, 1):
        st = wait_for(client, sid, sim_id)
        mark = "✔" if st == "completed" else "✘"
        logger.info("%s %s (%d/%d)", mark, code, i, len(launched))

    logger.info("Demo județe complet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
