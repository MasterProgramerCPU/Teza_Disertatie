"""Driver de campanie de benchmark.

Lanseaza prin API o matrice de simulari --- combinatii de
(set de date x model x limbaj x orizont t_max), repetate de un numar configurabil
de ori --- asteapta finalizarea fiecareia si colecteaza rezultatele intr-un CSV
si intr-un tabel sumar.

Acesta este levierul real pentru rulari ODE lungi si relevante: durata unei
rulari ODE nu depinde de marimea setului de date, ci de ``t_max`` (numarul de
pasi de integrare), de complexitatea modelului si de limbaj. Prin baleierea lui
``t_max`` peste mai multe modele si limbaje se obtine o campanie de benchmark
reproductibila si comparabila.

Pentru fiecare rulare se masoara latenta end-to-end pe partea de client
(de la crearea simularii pana la statusul ``completed``), care include coada
Redis, solver-ul si persistarea --- exact descompunerea discutata in capitolul
de evaluare software al lucrarii.

Exemplu:
    python run_benchmark.py \\
        --api-url http://localhost:8080 \\
        --email tudor@test.ro --password parola1234 \\
        --study <STUDY_ID> --dataset <DATASET_ID> \\
        --t-max 500 2000 10000 50000 --repeat 3 \\
        --output ../data/benchmark_results.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import statistics
import sys
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger("run_benchmark")

ALL_MODELS: tuple[str, ...] = ("sir", "sis", "seir", "sirs", "sidarthe", "lstm")
ODE_LANGUAGES: tuple[str, ...] = ("r", "julia", "python")
DEFAULT_T_MAX: tuple[int, ...] = (500, 2000, 10000, 50000)
POLL_INTERVAL_SEC = 1.5


@dataclass
class RunResult:
    dataset: str
    model: str
    language: str
    t_max: int
    repeat: int
    status: str
    elapsed_sec: float
    error: str = ""


class APIError(RuntimeError):
    pass


class Client:
    """Invelis subtire peste API-ul aplicatiei."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _data(self, resp: requests.Response) -> dict:
        try:
            body = resp.json()
        except ValueError:
            raise APIError(f"raspuns non-JSON ({resp.status_code}) de la {resp.url}")
        if resp.status_code >= 400 or "error" in body:
            msg = body.get("error", {}).get("message", resp.text)
            raise APIError(f"{resp.status_code}: {msg}")
        return body.get("data", {})

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

    def create_simulation(self, study: str, dataset: str, model: str,
                          language: str, t_max: int) -> str:
        resp = self.session.post(
            f"{self.base}/api/studies/{study}/simulations",
            json={
                "dataset_id": dataset,
                "model_type": model,
                "language": language,
                "t_max": t_max,
            },
            timeout=self.timeout,
        )
        run_id = self._data(resp).get("id")
        if not run_id:
            raise APIError("crearea simularii nu a returnat un id")
        return run_id

    def get_status(self, study: str, run_id: str) -> tuple[str, str]:
        resp = self.session.get(
            f"{self.base}/api/studies/{study}/simulations/{run_id}",
            timeout=self.timeout,
        )
        data = self._data(resp)
        return data.get("status", "unknown"), data.get("error_message") or ""


def build_matrix(datasets: list[str], models: list[str], languages: list[str],
                 t_max_values: list[int], repeat: int) -> list[tuple]:
    """Produce lista combinatiilor de rulat.

    LSTM este rulat doar de runner-ul dedicat, deci este fortat pe limbajul
    ``python`` si nu se multiplica pe celelalte limbaje.
    """
    combos: list[tuple] = []
    for dataset in datasets:
        for model in models:
            langs = ["python"] if model == "lstm" else languages
            for language in langs:
                for t_max in t_max_values:
                    for rep in range(1, repeat + 1):
                        combos.append((dataset, model, language, t_max, rep))
    return combos


def run_one(client: Client, study: str, dataset: str, model: str, language: str,
            t_max: int, rep: int, run_timeout: float) -> RunResult:
    base = RunResult(dataset, model, language, t_max, rep, "pending", 0.0)
    try:
        run_id = client.create_simulation(study, dataset, model, language, t_max)
    except APIError as exc:
        base.status, base.error = "create_failed", str(exc)
        return base

    start = time.perf_counter()
    deadline = start + run_timeout
    while True:
        time.sleep(POLL_INTERVAL_SEC)
        try:
            status, err = client.get_status(study, run_id)
        except APIError as exc:
            base.status, base.error = "poll_failed", str(exc)
            base.elapsed_sec = time.perf_counter() - start
            return base
        if status in ("completed", "failed"):
            base.status = status
            base.error = err
            base.elapsed_sec = time.perf_counter() - start
            return base
        if time.perf_counter() > deadline:
            base.status = "timeout"
            base.elapsed_sec = time.perf_counter() - start
            return base


def summarize(results: list[RunResult]) -> None:
    """Tabel sumar: latenta mediana per (model, limbaj, t_max)."""
    groups: dict[tuple, list[float]] = {}
    for r in results:
        if r.status == "completed":
            groups.setdefault((r.model, r.language, r.t_max), []).append(r.elapsed_sec)

    if not groups:
        logger.warning("nicio rulare completata --- nu exista sumar")
        return

    logger.info("%-10s %-8s %8s %6s %10s %10s", "model", "limbaj",
                "t_max", "n", "median(s)", "max(s)")
    for key in sorted(groups):
        model, language, t_max = key
        times = groups[key]
        logger.info("%-10s %-8s %8d %6d %10.2f %10.2f", model, language, t_max,
                    len(times), statistics.median(times), max(times))


def write_csv(results: list[RunResult], path: str) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["dataset", "model", "language", "t_max", "repeat",
                         "status", "elapsed_sec", "error"])
        for r in results:
            writer.writerow([r.dataset, r.model, r.language, r.t_max, r.repeat,
                             r.status, f"{r.elapsed_sec:.3f}", r.error])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Driver de campanie de benchmark.")
    parser.add_argument("--api-url", default="http://localhost:8080",
                        help="URL-ul de baza al API-ului (implicit: http://localhost:8080)")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--study", required=True, help="ID-ul studiului")
    parser.add_argument("--dataset", action="append", required=True,
                        help="ID de set de date (repetabil)")
    parser.add_argument("--model", action="append", default=None,
                        help=f"model de rulat (repetabil); implicit toate: {', '.join(ALL_MODELS)}")
    parser.add_argument("--language", action="append", default=None,
                        help=f"limbaj de rulat (repetabil); implicit: {', '.join(ODE_LANGUAGES)}")
    parser.add_argument("--t-max", type=int, nargs="+", default=list(DEFAULT_T_MAX),
                        help=f"valori t_max de baleiat (implicit: {' '.join(map(str, DEFAULT_T_MAX))})")
    parser.add_argument("--repeat", type=int, default=1,
                        help="numarul de repetari per combinatie (implicit: 1)")
    parser.add_argument("--run-timeout", type=float, default=600.0,
                        help="timeout per rulare, in secunde (implicit: 600)")
    parser.add_argument("--output", default="benchmark_results.csv",
                        help="fisierul CSV de iesire (implicit: benchmark_results.csv)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    models = args.model or list(ALL_MODELS)
    languages = args.language or list(ODE_LANGUAGES)
    for model in models:
        if model not in ALL_MODELS:
            logger.error("model necunoscut: %s (valide: %s)", model, ", ".join(ALL_MODELS))
            return 2
    for language in languages:
        if language not in ODE_LANGUAGES:
            logger.error("limbaj necunoscut: %s (valide: %s)", language, ", ".join(ODE_LANGUAGES))
            return 2

    client = Client(args.api_url)
    try:
        client.login(args.email, args.password)
    except (APIError, requests.RequestException) as exc:
        logger.error("autentificare esuata: %s", exc)
        return 1
    logger.info("autentificat la %s", args.api_url)

    matrix = build_matrix(args.dataset, models, languages, args.t_max, args.repeat)
    logger.info("campanie: %d rulari (%d seture x modele x limbaje x %d valori t_max x %d repetari)",
                len(matrix), len(args.dataset), len(args.t_max), args.repeat)

    results: list[RunResult] = []
    for idx, (dataset, model, language, t_max, rep) in enumerate(matrix, start=1):
        logger.info("[%d/%d] %s %s/%s t_max=%d (rep %d) ...",
                    idx, len(matrix), dataset[:8], model, language, t_max, rep)
        try:
            result = run_one(client, args.study, dataset, model, language,
                             t_max, rep, args.run_timeout)
        except requests.RequestException as exc:
            result = RunResult(dataset, model, language, t_max, rep,
                               "network_error", 0.0, str(exc))
        results.append(result)
        if result.status == "completed":
            logger.info("    completata in %.2f s", result.elapsed_sec)
        else:
            logger.warning("    %s: %s", result.status, result.error or "(fara mesaj)")

    write_csv(results, args.output)
    logger.info("rezultate scrise in %s", args.output)
    summarize(results)

    completed = sum(1 for r in results if r.status == "completed")
    logger.info("gata: %d/%d rulari completate", completed, len(results))
    return 0 if completed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
