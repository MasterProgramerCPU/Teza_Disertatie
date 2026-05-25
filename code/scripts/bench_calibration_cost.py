"""Costul software al calibrarii: cat costa o calibrare daca devine job in aplicatie.

Capitolul de comparatie si calibrare descrie calibrarea ca pe un tip de job
suplimentar in aplicatie. Spre deosebire de o simulare obisnuita, o calibrare
ruleaza zeci sau sute de integrari numerice candidate inainte de a produce un
singur set de parametri. Acest script masoara costul real al acestei operatii si
il proiecteaza in doua arhitecturi posibile.

Masurat direct (calibrare in-process, exact procedura din \\texttt{calibrate.py}):
  * numarul de simulari candidate = numarul de evaluari ale functiei obiectiv;
  * timp total wall-clock si timp CPU;
  * memorie de varf (\\texttt{tracemalloc}).

Proiectat in doua arhitecturi:
  * \\emph{naiv} --- fiecare simulare candidata este dispatch-uita ca job separat
    prin aplicatie (Redis -> runner -> scriere in YugabyteDB). Costul per job este
    masurat direct, lansand cateva simulari SIR reale prin API la orizontul ferestrei
    de calibrare; volumul de date scris in DB este numarul de simulari candidate
    inmultit cu numarul de puncte;
  * \\emph{recomandat} --- calibrarea ruleaza in-process intr-un singur job, iar in
    baza de date se scrie doar simularea finala (un singur set de rezultate).

Comparatia arata de ce calibrarea nu trebuie tratata ca N simulari independente:
overhead-ul de coada si de persistare, amortizat o singura data in design-ul
in-process, ar fi platit de N ori in cel naiv.

Output:
    docs/data/calibration_cost.csv
    docs/tables/calibration_cost.tex

Exemplu:
    python bench_calibration_cost.py \\
        --api-url http://localhost:8080 \\
        --email tudor@test.ro --password parola1234 \\
        --study <STUDY_ID> --dataset <DATASET_ID>
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd

# Reutilizam exact procedura de calibrare si clientul API deja existente.
import calibrate as cal
from run_benchmark import Client

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_OUT = REPO_ROOT / "docs" / "data"
TABLES_OUT = REPO_ROOT / "docs" / "tables"


class CountingLoss:
    """Inveleste functia obiectiv si numara evaluarile (= simulari candidate)."""

    def __init__(self, fn):
        self._fn = fn
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._fn(*args, **kwargs)


def load_window():
    """Reproduce fereastra de calibrare din calibrate.py (Romania, valul 1)."""
    df = pd.read_csv(cal.DATA_IN, parse_dates=["date"])
    n = float(df["population"].iloc[0])
    train = df[(df["date"] >= cal.TRAIN_START) & (df["date"] <= cal.TRAIN_END)].reset_index(drop=True)
    i0 = float(train["infected"].iloc[0])
    r0 = float(train["recovered"].iloc[0])
    y0 = [n - i0 - r0, i0, r0]
    t_train = np.arange(len(train), dtype=float)
    obs_train = train["infected"].astype(float).values
    return n, y0, t_train, obs_train, len(train)


def measure_inprocess(n, y0, t_train, obs_train) -> dict:
    """Ruleaza calibrarea (liber + constrans) cu instrumentare completa."""
    counter = CountingLoss(cal.loss_sir)
    cal.loss_sir = counter  # monkeypatch: numara fiecare integrare candidata

    tracemalloc.start()
    wall0 = time.perf_counter()
    cpu0 = time.process_time()

    bf, gf, lf = cal.calibrate_sir_free(n, y0, t_train, obs_train)
    bc, gc, lc = cal.calibrate_sir_fixed_gamma(n, y0, t_train, obs_train, cal.GAMMA_FIXED)

    wall_ms = (time.perf_counter() - wall0) * 1000.0
    cpu_ms = (time.process_time() - cpu0) * 1000.0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "candidates": counter.calls,
        "wall_ms": wall_ms,
        "cpu_ms": cpu_ms,
        "peak_mem_mb": peak / (1024.0 * 1024.0),
        "beta_free": bf, "gamma_free": gf,
        "beta_fixed": bc, "gamma_fixed": gc,
    }


def measure_job_cost(client: Client, study: str, dataset: str, t_max: int,
                     repeat: int) -> tuple[float, int]:
    """Masoara costul end-to-end al unui job SIR real prin aplicatie.

    Returneaza (latenta_mediana_ms_per_job, randuri_scrise_per_job).
    """
    latencies = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        run_id = client.create_simulation(study, dataset, "sir", "python", t_max)
        deadline = t0 + 120.0
        while True:
            time.sleep(0.4)
            status, _err = client.get_status(study, run_id)
            if status in ("completed", "failed"):
                break
            if time.perf_counter() > deadline:
                status = "timeout"
                break
        latencies.append((time.perf_counter() - t0) * 1000.0)
    rows_per_job = t_max + 1  # un rand per pas de integrare (0..t_max)
    return statistics.median(latencies), rows_per_job


def write_table(ip: dict, job_ms: float, rows_per_job: int, win_days: int,
                out_path: Path) -> None:
    n_cand = ip["candidates"]
    naive_jobs = n_cand
    naive_db_rows = n_cand * rows_per_job
    naive_proj_s = (n_cand * job_ms) / 1000.0
    reco_db_rows = rows_per_job  # doar simularea finala
    inproc_s = ip["wall_ms"] / 1000.0
    speedup = naive_proj_s / inproc_s if inproc_s > 0 else 0.0

    lines = [
        r"\begin{table*}[!htbp]",
        r"\centering",
        rf"\caption{{Costul software al calibrarii SIR (Romania, valul 1; fereastra de "
        rf"${win_days}$ zile, restart-uri multiple Nelder--Mead pentru scenariile liber si "
        r"constrans). Coloana \emph{in-process} masoara direct costul procedurii din "
        r"\texttt{calibrate.py}; coloana \emph{naiv (ca job-uri)} proiecteaza costul daca "
        r"fiecare simulare candidata ar fi un job separat prin aplicatie, folosind latenta "
        rf"end-to-end masurata a unui job SIR real (${job_ms:.0f}$~ms/job); coloana "
        r"\emph{recomandat} corespunde calibrarii intr-un singur job, cu o singura simulare "
        r"finala scrisa in baza de date. Numarul de simulari candidate este numarul real de "
        r"evaluari ale functiei obiectiv.}",
        r"\label{tab:calibration_cost}",
        r"\small",
        r"\begin{tabularx}{\textwidth}{X r r r}",
        r"\toprule",
        r"\textbf{Marime} & \textbf{In-process} & \textbf{Naiv (ca job-uri)} & "
        r"\textbf{Recomandat} \\",
        r"\midrule",
        rf"Simulari candidate & {n_cand} & {n_cand} & {n_cand} \\",
        rf"Job-uri prin aplicatie & 1 & {naive_jobs} & 1 \\",
        rf"Randuri scrise in DB & 0 & {naive_db_rows} & {reco_db_rows} \\",
        r"\midrule",
        rf"Timp total wall (s) & {inproc_s:.2f} & {naive_proj_s:.1f}\textsuperscript{{*}} & "
        rf"{inproc_s:.2f} \\",
        rf"Timp CPU (s) & {ip['cpu_ms'] / 1000.0:.2f} & --- & {ip['cpu_ms'] / 1000.0:.2f} \\",
        rf"Memorie de varf (MB) & {ip['peak_mem_mb']:.1f} & --- & {ip['peak_mem_mb']:.1f} \\",
        r"\bottomrule",
        r"\end{tabularx}",
        rf"\\[2pt]\footnotesize\textsuperscript{{*}}~Proiectat: "
        rf"${n_cand} \times {job_ms:.0f}$~ms${{}}={naive_proj_s:.0f}$~s; de "
        rf"$\sim${speedup:.0f}$\times$ mai scump decat calibrarea in-process, fara castig "
        r"de acuratete --- overhead-ul de coada si persistare ar fi platit pentru fiecare "
        r"integrare candidata.",
        r"\end{table*}",
    ]
    out_path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cost software al calibrarii.")
    p.add_argument("--api-url", default="http://localhost:8080")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--study", required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--job-repeat", type=int, default=8,
                   help="numar de job-uri SIR reale pentru estimarea costului per job")
    args = p.parse_args(argv)

    DATA_OUT.mkdir(parents=True, exist_ok=True)
    TABLES_OUT.mkdir(parents=True, exist_ok=True)

    n, y0, t_train, obs_train, win_days = load_window()
    print(f"Fereastra calibrare: {win_days} zile (Romania, valul 1)")

    print("\n=== Cost in-process (calibrare reala) ===")
    ip = measure_inprocess(n, y0, t_train, obs_train)
    print(f"  simulari candidate : {ip['candidates']}")
    print(f"  wall               : {ip['wall_ms'] / 1000.0:.2f} s")
    print(f"  CPU                : {ip['cpu_ms'] / 1000.0:.2f} s")
    print(f"  memorie de varf    : {ip['peak_mem_mb']:.1f} MB")
    print(f"  beta_free={ip['beta_free']:.4f} gamma_free={ip['gamma_free']:.4f} | "
          f"beta_fixed={ip['beta_fixed']:.4f}")

    print(f"\n=== Cost per job real (SIR, t_max={win_days}, {args.job_repeat} job-uri) ===")
    client = Client(args.api_url)
    client.login(args.email, args.password)
    job_ms, rows_per_job = measure_job_cost(client, args.study, args.dataset,
                                            win_days, args.job_repeat)
    print(f"  latenta mediana per job : {job_ms:.0f} ms")
    print(f"  randuri scrise per job  : {rows_per_job}")

    naive_proj_s = (ip["candidates"] * job_ms) / 1000.0
    print(f"\n  Proiectie naiv (ca job-uri): {ip['candidates']} x {job_ms:.0f} ms "
          f"= {naive_proj_s:.0f} s  (vs {ip['wall_ms'] / 1000.0:.2f} s in-process)")

    # CSV
    with open(DATA_OUT / "calibration_cost.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        w.writerow(["candidates", ip["candidates"]])
        w.writerow(["inprocess_wall_s", round(ip["wall_ms"] / 1000.0, 3)])
        w.writerow(["inprocess_cpu_s", round(ip["cpu_ms"] / 1000.0, 3)])
        w.writerow(["peak_mem_mb", round(ip["peak_mem_mb"], 2)])
        w.writerow(["job_latency_ms", round(job_ms, 1)])
        w.writerow(["rows_per_job", rows_per_job])
        w.writerow(["naive_proj_wall_s", round(naive_proj_s, 1)])
        w.writerow(["naive_db_rows", ip["candidates"] * rows_per_job])
    print(f"\n-> {(DATA_OUT / 'calibration_cost.csv').relative_to(REPO_ROOT)}")

    write_table(ip, job_ms, rows_per_job, win_days, TABLES_OUT / "calibration_cost.tex")
    print(f"-> {(TABLES_OUT / 'calibration_cost.tex').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
