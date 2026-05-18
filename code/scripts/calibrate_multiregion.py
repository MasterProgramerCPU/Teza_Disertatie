"""Calibrare SIR multi-regiune pe valul 1 COVID-19 (martie - septembrie 2020).

Aplica aceeasi procedura ca in :mod:`calibrate` (gamma fix din literatura,
optimizeaza doar beta prin Nelder-Mead) pe patru tari europene cu scari de
populatie si timing-uri ale valului 1 diferite. Scopul este sa arate ca
framework-ul de calibrare functioneaza cross-regiune, nu doar pentru cazul
particular Romania, si sa produca un tabel comparativ al parametrilor
estimati.

Output:
    docs/data/calibration_multiregion.csv  - observat + fit + forecast pe 4 tari
    docs/tables/calibration_multiregion.tex - tabel comparativ beta, R0, MAE
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import minimize

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_IN_DIR = REPO_ROOT / "code" / "data" / "processed"
DATA_OUT = REPO_ROOT / "docs" / "data"
TABLES_OUT = REPO_ROOT / "docs" / "tables"

# Fereastra de calibrare (aceeasi pentru toate tarile, ca sa fie comparabila).
TRAIN_START = pd.Timestamp("2020-03-15")
TRAIN_END = pd.Timestamp("2020-08-15")
TEST_END = pd.Timestamp("2020-09-15")
GAMMA_FIXED = 1.0 / 14.0
SEED = 7

# Tarile pentru calibrare. (slug fisier, nume romanesc, populatie nominala)
COUNTRIES = [
    ("romania", "Romania"),
    ("italy",   "Italia"),
    ("germany", "Germania"),
    ("spain",   "Spania"),
]


def sir_rhs(t, y, beta, gamma, n):
    s, i, _r = y
    new = beta * s * i / n
    return [-new, new - gamma * i, gamma * i]


def simulate(beta, gamma, n, y0, t_eval):
    sol = solve_ivp(
        sir_rhs, (t_eval[0], t_eval[-1]), y0,
        args=(beta, gamma, n), method="RK45",
        t_eval=t_eval, rtol=1e-8, atol=1e-10,
    )
    return sol.y if sol.success else None


def calibrate_beta(n, y0, t_train, obs_train, gamma) -> tuple[float, float]:
    rng = np.random.default_rng(SEED)
    best = (None, np.inf)
    for _ in range(5):
        beta0 = float(rng.uniform(0.05, 1.0))
        res = minimize(
            lambda b: float(np.mean((simulate(b[0], gamma, n, y0, t_train)[1] - obs_train) ** 2))
                       if b[0] > 0 else 1e18,
            x0=[beta0], method="Nelder-Mead",
            options={"xatol": 1e-6, "fatol": 1e-3, "maxiter": 1000, "adaptive": True},
        )
        if res.fun < best[1]:
            best = (float(res.x[0]), float(res.fun))
    return best


def mae(a, b): return float(np.mean(np.abs(a - b)))
def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))


def main() -> int:
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    TABLES_OUT.mkdir(parents=True, exist_ok=True)

    results = []
    csv_panels: dict[str, pd.DataFrame] = {}

    for slug, label in COUNTRIES:
        df = pd.read_csv(DATA_IN_DIR / f"{slug}.csv", parse_dates=["date"])
        n = float(df["population"].iloc[0])
        train = df[(df["date"] >= TRAIN_START) & (df["date"] <= TRAIN_END)].reset_index(drop=True)
        test = df[(df["date"] > TRAIN_END) & (df["date"] <= TEST_END)].reset_index(drop=True)
        full = df[(df["date"] >= TRAIN_START) & (df["date"] <= TEST_END)].reset_index(drop=True)

        i0 = float(train["infected"].iloc[0])
        r0 = float(train["recovered"].iloc[0])
        s0 = n - i0 - r0
        y0 = [s0, i0, r0]

        t_train = np.arange(len(train), dtype=float)
        t_full = np.arange(len(full), dtype=float)
        obs_train = train["infected"].astype(float).values
        obs_test = test["infected"].astype(float).values
        obs_full = full["infected"].astype(float).values

        beta, _mse_t = calibrate_beta(n, y0, t_train, obs_train, GAMMA_FIXED)
        fit_full = simulate(beta, GAMMA_FIXED, n, y0, t_full)[1]
        fit_train = fit_full[:len(train)]
        fit_test = fit_full[len(train):]

        results.append({
            "label": label, "n": n, "i0": i0,
            "beta": beta, "R0": beta / GAMMA_FIXED,
            "mae_train": mae(obs_train, fit_train),
            "rmse_train": rmse(obs_train, fit_train),
            "mae_test": mae(obs_test, fit_test),
            "rmse_test": rmse(obs_test, fit_test),
        })
        print(f"{label:10s}  N={n:>12.0f}  I0={i0:>7.0f}  "
              f"beta={beta:.4f}  R0={beta/GAMMA_FIXED:.2f}  "
              f"MAE_train={mae(obs_train, fit_train):.0f}  MAE_test={mae(obs_test, fit_test):.0f}")

        csv_panels[slug] = pd.DataFrame({
            "day": t_full.astype(int),
            "observed": obs_full.astype(int),
            "fit": np.where(t_full < len(train), fit_full, np.nan),
            "pred": np.where(t_full >= len(train), fit_full, np.nan),
        })

    # CSV unic cu toate tarile in format wide pentru pgfplots
    merged = csv_panels["romania"][["day"]].copy()
    for slug, _ in COUNTRIES:
        d = csv_panels[slug]
        merged[f"obs_{slug}"] = d["observed"]
        merged[f"fit_{slug}"] = d["fit"]
        merged[f"pred_{slug}"] = d["pred"]
    merged.to_csv(DATA_OUT / "calibration_multiregion.csv", index=False)
    print(f"\nScris: {DATA_OUT.relative_to(REPO_ROOT)}/calibration_multiregion.csv")

    # Tabel LaTeX comparativ
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Calibrare SIR cross-regiune pe valul 1 al pandemiei COVID-19 "
        r"($15$~martie -- $15$~august 2020 antrenare, $16$~august -- $15$~septembrie 2020 test). "
        r"In toate cele patru cazuri $\gamma$ este fixat la valoarea de literatura "
        r"$1/14$ zile, iar $\beta$ este optimizat prin Nelder-Mead. "
        r"Valorile $\hat\beta$ si $\hat{\mathcal{R}}_0$ sunt comparabile direct intre tari, "
        r"dar erorile absolute reflecta scarile diferite de populatie (column N) si de I$_0$.}",
        r"\label{tab:calibration_multiregion}",
        r"\begin{tabularx}{\textwidth}{l r r r r X r r}",
        r"\toprule",
        r"\textbf{Tara} & \textbf{N (mil.)} & \textbf{$I_0$} & "
        r"\textbf{$\hat\beta$} & \textbf{$\hat{\mathcal{R}}_0$} & "
        r"\textbf{Observatii} & \textbf{MAE train} & \textbf{MAE test} \\",
        r"\midrule",
    ]
    notes = {
        "Romania": "infectie inca incipienta la inceputul ferestrei",
        "Italia": "deja in plin val 1 ($I_0 \\sim 20\\,000$)",
        "Germania": "raspuns puternic la masuri",
        "Spania": "val 2 incepe sa creasca la finalul ferestrei",
    }
    for r in results:
        n_mil = r["n"] / 1e6
        lines.append(
            f"\\textbf{{{r['label']}}} & ${n_mil:.1f}$ & ${r['i0']:.0f}$ & "
            f"${r['beta']:.4f}$ & ${r['R0']:.2f}$ & "
            f"{notes[r['label']]} & "
            f"${r['mae_train']:.0f}$ & ${r['mae_test']:.0f}$ \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table*}"]
    (TABLES_OUT / "calibration_multiregion.tex").write_text("\n".join(lines) + "\n")
    print(f"Scris: {TABLES_OUT.relative_to(REPO_ROOT)}/calibration_multiregion.tex")
    return 0


if __name__ == "__main__":
    sys.exit(main())
