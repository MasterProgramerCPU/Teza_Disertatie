"""Adauga un utilizator ca membru in toate studiile.

Utilitar de administrare: ruleaza prin API, ca super-admin, si adauga un cont
(dupa email) in fiecare studiu existent, cu un rol dat. Util pentru a putea
rula simulari dintr-un cont dedicat (de exemplu un cont de cercetator) fara a-l
adauga manual in zeci de studii.

Idempotent: daca utilizatorul e deja membru intr-un studiu, acel studiu este
sarit (raspuns 409 de la API).

Exemplu:
    python grant_membership.py --api-url http://localhost:8080 \\
        --admin-email tudor@test.ro --admin-password parola1234 \\
        --email cercetator@demo.ro --role researcher
"""

from __future__ import annotations

import argparse
import logging
import sys

import requests

logger = logging.getLogger("grant_membership")

VALID_ROLES = ("admin", "researcher", "contributor", "viewer")


class APIError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class Client:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _data(self, resp: requests.Response):
        try:
            body = resp.json()
        except ValueError:
            raise APIError(resp.status_code, f"raspuns non-JSON de la {resp.url}")
        if resp.status_code >= 400 or (isinstance(body, dict) and "error" in body):
            msg = body.get("error", {}).get("message", resp.text) if isinstance(body, dict) else resp.text
            raise APIError(resp.status_code, msg)
        return body.get("data", {}) if isinstance(body, dict) else body

    def login(self, email: str, password: str) -> None:
        resp = self.session.post(f"{self.base}/api/auth/login",
                                 json={"email": email, "password": password},
                                 timeout=self.timeout)
        token = self._data(resp).get("token")
        if not token:
            raise APIError(resp.status_code, "login a reusit dar nu a returnat token")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def list_studies(self) -> list[dict]:
        return self._data(self.session.get(f"{self.base}/api/studies", timeout=self.timeout))

    def add_member(self, study_id: str, email: str, role: str) -> None:
        resp = self.session.post(f"{self.base}/api/studies/{study_id}/members",
                                 json={"email": email, "role": role},
                                 timeout=self.timeout)
        self._data(resp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Adauga un utilizator in toate studiile.")
    parser.add_argument("--api-url", default="http://localhost:8080",
                        help="URL-ul de baza al API-ului (implicit: http://localhost:8080)")
    parser.add_argument("--admin-email", required=True, help="cont super-admin pentru autentificare")
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--email", required=True, help="utilizatorul de adaugat in studii")
    parser.add_argument("--role", default="researcher", choices=VALID_ROLES,
                        help="rolul acordat in fiecare studiu (implicit: researcher)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    client = Client(args.api_url)
    try:
        client.login(args.admin_email, args.admin_password)
        studies = client.list_studies()
    except (APIError, requests.RequestException) as exc:
        logger.error("nu pot porni: %s", exc)
        return 1

    logger.info("%d studii gasite; adaug '%s' cu rolul '%s'",
                len(studies), args.email, args.role)

    added = skipped = failed = 0
    for study in studies:
        sid, name = study["id"], study["name"]
        try:
            client.add_member(sid, args.email, args.role)
            logger.info("[%s] adaugat", name)
            added += 1
        except APIError as exc:
            if exc.status == 409:
                logger.debug("[%s] deja membru -- sar", name)
                skipped += 1
            else:
                logger.error("[%s] esuat: %s", name, exc.message)
                failed += 1
        except requests.RequestException as exc:
            logger.error("[%s] eroare de retea: %s", name, exc)
            failed += 1

    logger.info("gata -- adaugat in %d studii, %d deja membru, %d esuate",
                added, skipped, failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
