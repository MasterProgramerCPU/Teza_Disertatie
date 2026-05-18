"""Benchmark standalone al solverului Python pe hardware-ul local.

Ruleaza aceeasi matrice de modele compartimentale ca runner-ul Python din
container (\\texttt{runner-python}), folosind \\texttt{scipy.solve\\_ivp} cu
aceleasi tolerante si acelasi solver (RK45). Spre deosebire de campania de
benchmark prin aplicatie (capitolul de evaluare), aici se masoara doar costul
\\emph{solverului} pe hardware-ul gazda --- fara cost de container, fara
inserari in baza de date, fara coada Redis.

Scopul: caracterizarea variabilitatii cross-hardware pentru aceeasi
implementare Python, complementar campaniei deja rulate pe cluster.

Cluster (deja masurat): runner Python in container, pe OpenStack VM amd64
(4 vCPU / 8 GiB), cu wall_time_ms inclusiv inserarile in YugabyteDB.

Local (acest script): Python nativ pe Apple M1 Pro arm64, fara container,
fara DB. Diferenta intre cele doua reflecta combinatia hardware host +
overhead container + persistare, nu doar diferenta de hardware brut.

Usage:
    python bench_local_solver.py
        --workload romania      # trivial (I0=0, ca pe cluster)
        --workload synthetic    # non-trivial (I0=100)
        --t-max 365 2000 10000
        --repeat 3
        --output ../../docs/data/bench_local_m1.csv
"""

from __future__ import annotations

import argparse
import csv
import platform
import sys
import time
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

REPO_ROOT = Path(__file__).resolve().parents[2]

# Parametri impliciti din API (defaultParameters din simulations.go)
PARAMS = {
    "sis":  {"beta": 0.3, "gamma": 0.0714},
    "sir":  {"beta": 0.3, "gamma": 0.0714},
    "seir": {"beta": 0.3, "sigma": 0.1923, "gamma": 0.0714},
    "sirs": {"beta": 0.3, "gamma": 0.0714, "xi": 0.0055},
    "sidarthe": {
        "alpha": 0.57, "beta": 0.011, "gamma": 0.456, "delta": 0.011,
        "epsilon": 0.171, "zeta": 0.125, "lambda": 0.034,
        "eta": 0.125, "rho": 0.034, "theta": 0.370, "mu": 0.017,
        "kappa": 0.017, "nu": 0.027, "xi": 0.017, "sigma": 0.017, "tau": 0.010,
    },
}

# Workloads (initial conditions). 'romania' reproduce exact ce a folosit
# campania pe cluster (primul rand din romania.csv: I=0, trivial).
WORKLOADS = {
    "romania":   {"n": 19_659_270, "i0": 0,    "label": "Romania OWID (primul rand)"},
    "synthetic": {"n": 50_000_000, "i0": 100,  "label": "Synthetic multiwave (I0=100, non-trivial)"},
}


# ---- RHS-uri (aliniate cu runner-ul Python din container) ----------------

def sis_rhs(t, y, p, n):
    s, i = y
    new = p["beta"] * s * i / n
    rec = p["gamma"] * i
    return [-new + rec, new - rec]


def sir_rhs(t, y, p, n):
    s, i, _r = y
    return [-p["beta"] * s * i / n,
            p["beta"] * s * i / n - p["gamma"] * i,
            p["gamma"] * i]


def seir_rhs(t, y, p, n):
    s, e, i, _r = y
    new = p["beta"] * s * i / n
    return [-new, new - p["sigma"] * e,
            p["sigma"] * e - p["gamma"] * i, p["gamma"] * i]


def sirs_rhs(t, y, p, n):
    s, i, r = y
    new = p["beta"] * s * i / n
    rec = p["gamma"] * i
    waning = p["xi"] * r
    return [-new + waning, new - rec, rec - waning]


def sidarthe_rhs(t, y, p, n):
    s, i, d, a, r, threat, _h, _e = y
    force = (p["alpha"] * i + p["beta"] * d + p["gamma"] * a + p["delta"] * r) / n
    new = s * force
    return [
        -new,
        new - (p["epsilon"] + p["zeta"] + p["lambda"]) * i,
        p["epsilon"] * i - (p["eta"] + p["rho"]) * d,
        p["zeta"] * i - (p["theta"] + p["mu"] + p["kappa"]) * a,
        p["eta"] * d + p["theta"] * a - (p["nu"] + p["xi"]) * r,
        p["mu"] * a + p["nu"] * r - (p["sigma"] + p["tau"]) * threat,
        p["lambda"] * i + p["rho"] * d + p["kappa"] * a + p["xi"] * r + p["sigma"] * threat,
        p["tau"] * threat,
    ]


RHS = {"sis": sis_rhs, "sir": sir_rhs, "seir": seir_rhs,
       "sirs": sirs_rhs, "sidarthe": sidarthe_rhs}


def initial_conditions(model: str, n: float, i0: float) -> list[float]:
    s0 = n - i0
    if model == "sis":
        return [s0, i0]
    if model in ("sir", "sirs"):
        return [s0, i0, 0.0]
    if model == "seir":
        return [s0, 0.0, i0, 0.0]
    if model == "sidarthe":
        return [s0, i0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    raise ValueError(model)


def run_one(model: str, t_max: int, n: float, i0: float) -> tuple[float, float]:
    """Returneaza (wall_ms, cpu_ms) pentru o singura rulare."""
    p = PARAMS[model]
    y0 = initial_conditions(model, n, i0)
    t_eval = np.arange(0, t_max + 1, dtype=float)

    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    sol = solve_ivp(
        fun=RHS[model],
        t_span=(0.0, float(t_max)),
        y0=y0,
        method="RK45",
        t_eval=t_eval,
        args=(p, float(n)),
        rtol=1e-8, atol=1e-10,
    )
    wall_ms = (time.perf_counter() - wall_start) * 1000.0
    cpu_ms = (time.process_time() - cpu_start) * 1000.0
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed pentru {model}/{t_max}: {sol.message}")
    return wall_ms, cpu_ms


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workload", action="append", default=None,
                   help=f"workload-uri (repetabil); implicit toate: {', '.join(WORKLOADS)}")
    p.add_argument("--model", action="append", default=None,
                   help="modele (repetabil); implicit toate")
    p.add_argument("--t-max", type=int, nargs="+", default=[365, 2000, 10000],
                   help="valori t_max (implicit 365 2000 10000)")
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--warmup", type=int, default=1,
                   help="rulari de incalzire ignorate (implicit 1)")
    p.add_argument("--output", default=str(REPO_ROOT / "docs" / "data" / "bench_local_m1.csv"))
    args = p.parse_args(argv)

    workloads = args.workload or list(WORKLOADS)
    models = args.model or list(PARAMS)
    rows = []

    print(f"Hardware: {platform.machine()} / {platform.processor() or platform.system()}")
    print(f"Python: {sys.version.split()[0]}, scipy via solve_ivp RK45")
    print(f"Workload(s): {workloads}, modele: {models}, t_max: {args.t_max}, "
          f"repetari: {args.repeat} (+ {args.warmup} warmup)")
    print()

    for wl in workloads:
        wl_cfg = WORKLOADS[wl]
        for model in models:
            for t_max in args.t_max:
                # warmup
                for _ in range(args.warmup):
                    run_one(model, t_max, wl_cfg["n"], wl_cfg["i0"])
                # masurare
                walls = []
                cpus = []
                for rep in range(1, args.repeat + 1):
                    w, c = run_one(model, t_max, wl_cfg["n"], wl_cfg["i0"])
                    walls.append(w)
                    cpus.append(c)
                    rows.append({
                        "hardware": "M1 Pro (arm64, nativ)",
                        "workload": wl, "model": model, "t_max": t_max,
                        "repeat": rep,
                        "wall_ms": round(w, 3), "cpu_ms": round(c, 3),
                    })
                med_w = sorted(walls)[len(walls) // 2]
                print(f"  [{wl:9s}] {model:8s} t_max={t_max:>6} -> "
                      f"wall median={med_w:7.3f} ms  (rep wall: "
                      f"{', '.join(f'{x:.2f}' for x in walls)})")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nScris {len(rows)} masuratori in {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
