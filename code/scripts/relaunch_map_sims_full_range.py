"""Re-lansează simulările demo de hartă cu t_max=1400 zile (acoperă tot intervalul observat).

Pentru fiecare studiu folosit în pagina Hartă, lansează o nouă simulare
SIR/Python cu t_max=1400 (≈ perioada observată 2020-2023). Pentru
sub-național, β e variat per regiune după codul ISO 3166-2 (același mecanism
ca în seed_country_subregions.py) ca harta să rămână vizibil eterogenă.

Backend-ul Map alege „cea mai recentă completed", deci sims-urile noi
înlocuiesc automat cele cu t_max=365 ca afișaj curent.

Exemplu:
    python relaunch_map_sims_full_range.py \\
        --email cercetator@demo.ro --password demo1234parola
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time

import requests

logger = logging.getLogger("relaunch_map")

# Studiile folosite vizual pe pagina Hartă
TARGET_STUDIES = {
    "Demo Hartă — COVID-19 selecție globală",
    "Demo Hartă — Romania focus",
    "Demo Hartă — Romania pe județe",
    "COVID-19 — World OWID complet (2020-2024)",
    "COVID-19 — USA pe state-uri (JHU CSSE)",
    "Demo Hartă — China pe provincii",
    "Demo Hartă — Canada pe provincii",
    "Demo Hartă — Australia pe state-uri",
    "Demo Hartă — France pe DOM/TOM",
}

T_MAX = 1400  # ≈ zile între 2020-01-22 și 2023-12-31 (acoperă majoritatea
              # ferestrei observate per regiune, indiferent de când a debutat
              # primul caz)


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

    def studies(self):
        data = self._data(self.session.get(f"{self.base}/api/studies", timeout=30))
        return [item["study"] for item in (data or []) if isinstance(item, dict) and item.get("study")]

    def datasets(self, sid):
        return self._data(self.session.get(
            f"{self.base}/api/studies/{sid}/datasets", timeout=60
        )) or []

    def create_simulation(self, sid, dataset, t_max, parameters=None):
        payload = {"dataset_id": dataset, "model_type": "sir",
                   "language": "python", "t_max": t_max}
        if parameters:
            payload["parameters"] = parameters
        return self._data(self.session.post(
            f"{self.base}/api/studies/{sid}/simulations",
            json=payload, timeout=30,
        ))["id"]


def beta_for_region(region_code: str) -> float:
    """β determinist per regiune. Pentru coduri ISO 3166-2 (RO-CJ, US-CA),
    rezultă variație fină. Pentru ISO3 (ROU, USA), rezultă variație țară.
    """
    h = int(hashlib.sha256(region_code.encode()).hexdigest()[:8], 16)
    return round(0.30 * (0.55 + (h % 1000) / 1000.0), 4)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", default="http://127.0.0.1:8080")
    p.add_argument("--host-header", default="sir-workbench.ro")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--t-max", type=int, default=T_MAX)
    args = p.parse_args(argv)
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)

    client = Client(args.api_url, host_header=args.host_header)
    try:
        client.login(args.email, args.password)
    except Exception as e:  # noqa: BLE001
        logger.error("login: %s", e)
        return 1

    total = 0
    for st in client.studies():
        if st["name"] not in TARGET_STUDIES:
            continue
        try:
            datasets = client.datasets(st["id"])
        except Exception as e:  # noqa: BLE001
            logger.warning("[%s] eșec listare: %s", st["name"], e)
            continue
        for ds in datasets:
            # Nume dataset = de obicei codul de regiune (RO-CJ, US-CA, ROU etc.)
            region_code = ds["name"]
            beta = beta_for_region(region_code)
            try:
                client.create_simulation(
                    st["id"], ds["id"], args.t_max,
                    parameters={"beta": beta, "gamma": 0.0714},
                )
                total += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] %s: %s", st["name"], region_code, e)
            time.sleep(0.02)
        logger.info("[%s] %d dataset-uri relansate", st["name"], len(datasets))
    logger.info("Total: %d simulări lansate cu t_max=%d", total, args.t_max)
    return 0


if __name__ == "__main__":
    sys.exit(main())
