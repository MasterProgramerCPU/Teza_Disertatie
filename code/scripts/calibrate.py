"""Calibrare SIR pe date COVID-19 reale (Romania, valul 1 din 2020).

Compara doua scenarii pe acelasi set de date:
  * \\emph{liber}: optimizeaza ambele rate (beta, gamma) prin Nelder-Mead;
  * \\emph{constrans}: foloseste gamma fix din literatura clinica (1/14 zile)
    si optimizeaza doar beta.

In paralel calculeaza pierderea pe o grila 2D in (beta, gamma) pentru
vizualizarea peisajului de pierdere si discutia identifiabilitatii practice.

Calibrarea SIDARTHE pe acelasi tip de date (cazuri active observabile, fara
distinctia testare/spitalizare/ATI) este ill-posed pentru cele 16 rate; este
mentionata ca directie viitoare in cap. 10.

Output:
    docs/data/calibration_sir_romania.csv  - obs vs fit liber/constrans
    docs/data/identifiability_grid_sir.csv - peisaj de pierdere 2D
    docs/tables/calibration_results.tex    - tabel comparativ liber vs constrans
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import minimize

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_IN = REPO_ROOT / "code" / "data" / "processed" / "romania.csv"
DATA_OUT = REPO_ROOT / "docs" / "data"
TABLES_OUT = REPO_ROOT / "docs" / "tables"

# Fereastra de calibrare: valul 1 in Romania.
TRAIN_START = pd.Timestamp("2020-03-15")
TRAIN_END = pd.Timestamp("2020-08-15")
TEST_END = pd.Timestamp("2020-09-15")

SEED = 42

# Pentru analiza identifiabilitatii: grila 2D in (beta, gamma).
GRID_BETA = np.linspace(0.05, 0.60, 56)
GRID_GAMMA = np.linspace(0.05, 0.40, 36)

# Constrangere din literatura clinica pentru COVID-19: durata infectioasa ~14 zile.
GAMMA_FIXED = 1.0 / 14.0


# ---- Modele ---------------------------------------------------------------

def sir_rhs(t, y, beta, gamma, n):
    s, i, _r = y
    new = beta * s * i / n
    return [-new, new - gamma * i, gamma * i]


# ---- Loss + optimizare ----------------------------------------------------

def simulate_sir(beta, gamma, n, y0, t_eval):
    sol = solve_ivp(
        sir_rhs, (t_eval[0], t_eval[-1]), y0,
        args=(beta, gamma, n), method="RK45",
        t_eval=t_eval, rtol=1e-8, atol=1e-10,
    )
    return sol.y if sol.success else None


def loss_sir(theta, n, y0, t_train, observed_train):
    beta, gamma = theta
    if beta <= 0 or gamma <= 0 or beta > 5 or gamma > 5:
        return 1e18
    y = simulate_sir(beta, gamma, n, y0, t_train)
    if y is None:
        return 1e18
    fit = y[1]  # I(t)
    # MSE pe scara originala — observatii infectati activi
    return float(np.mean((fit - observed_train) ** 2))


def calibrate_sir_free(n, y0, t_train, observed_train) -> tuple[float, float, float]:
    """Calibrare libera: optimizeaza (beta, gamma) simultan."""
    rng = np.random.default_rng(SEED)
    best = (None, None, np.inf)
    for _ in range(8):
        beta0 = float(rng.uniform(0.1, 0.8))
        gamma0 = float(rng.uniform(1 / 21, 1 / 4))
        res = minimize(
            loss_sir, x0=[beta0, gamma0],
            args=(n, y0, t_train, observed_train),
            method="Nelder-Mead",
            options={"xatol": 1e-6, "fatol": 1e-3, "maxiter": 2000, "adaptive": True},
        )
        if res.fun < best[2]:
            best = (float(res.x[0]), float(res.x[1]), float(res.fun))
    return best


def calibrate_sir_fixed_gamma(n, y0, t_train, observed_train, gamma_fixed: float):
    """Calibrare constransa: gamma fix din literatura, optimizeaza doar beta."""
    rng = np.random.default_rng(SEED)
    best = (None, np.inf)
    for _ in range(5):
        beta0 = float(rng.uniform(0.05, 1.0))
        res = minimize(
            lambda b: loss_sir([b[0], gamma_fixed], n, y0, t_train, observed_train),
            x0=[beta0], method="Nelder-Mead",
            options={"xatol": 1e-6, "fatol": 1e-3, "maxiter": 1000, "adaptive": True},
        )
        if res.fun < best[1]:
            best = (float(res.x[0]), float(res.fun))
    return best[0], gamma_fixed, best[1]


def loss_grid(n, y0, t_train, observed_train) -> pd.DataFrame:
    """Grila 2D in (beta, gamma) pentru vizualizarea peisajului de pierdere."""
    rows = []
    for beta in GRID_BETA:
        for gamma in GRID_GAMMA:
            mse = loss_sir([beta, gamma], n, y0, t_train, observed_train)
            rows.append((float(beta), float(gamma), float(mse)))
    return pd.DataFrame(rows, columns=["beta", "gamma", "mse"])


# ---- Metrici --------------------------------------------------------------

def mae(a, b): return float(np.mean(np.abs(a - b)))
def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))


# ---- Pipeline -------------------------------------------------------------

def main() -> int:
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    TABLES_OUT.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_IN, parse_dates=["date"])
    n = float(df["population"].iloc[0])

    train = df[(df["date"] >= TRAIN_START) & (df["date"] <= TRAIN_END)].reset_index(drop=True)
    test = df[(df["date"] > TRAIN_END) & (df["date"] <= TEST_END)].reset_index(drop=True)
    full = df[(df["date"] >= TRAIN_START) & (df["date"] <= TEST_END)].reset_index(drop=True)
    print(f"Fereastra: {TRAIN_START.date()} -> {TEST_END.date()}  "
          f"(train {len(train)} zile, test {len(test)} zile)")

    # condi initiale din primul rand al ferestrei
    i0 = float(train["infected"].iloc[0])
    r0 = float(train["recovered"].iloc[0])
    s0 = n - i0 - r0
    y0_sir = [s0, i0, r0]
    print(f"Conditii initiale SIR: S={s0:.0f}, I={i0:.0f}, R={r0:.0f}")

    t_train = np.arange(len(train), dtype=float)
    t_full = np.arange(len(full), dtype=float)
    obs_train = train["infected"].astype(float).values
    obs_full = full["infected"].astype(float).values

    obs_test = test["infected"].astype(float).values

    def evaluate(beta, gamma, label):
        y = simulate_sir(beta, gamma, n, y0_sir, t_full)
        fit = y[1]
        return {
            "label": label, "beta": beta, "gamma": gamma, "R0": beta / gamma,
            "fit_full": fit,
            "mae_train": mae(obs_train, fit[:len(train)]),
            "rmse_train": rmse(obs_train, fit[:len(train)]),
            "mae_test": mae(obs_test, fit[len(train):]),
            "rmse_test": rmse(obs_test, fit[len(train):]),
        }

    # ---- SIR liber: optimizare (beta, gamma) ----
    print("\n=== SIR liber: optimizeaza (beta, gamma) ===")
    bf, gf, lf = calibrate_sir_free(n, y0_sir, t_train, obs_train)
    free_res = evaluate(bf, gf, "free")
    print(f"  beta={bf:.4f}, gamma={gf:.4f} (1/{1/gf:.1f} zile), R0={bf/gf:.2f}")
    print(f"  MAE_train={free_res['mae_train']:.0f}, MAE_test={free_res['mae_test']:.0f}")

    # ---- SIR constrans: gamma fix din literatura ----
    print(f"\n=== SIR constrans: gamma = 1/14 = {GAMMA_FIXED:.4f} ===")
    bc, gc, lc = calibrate_sir_fixed_gamma(n, y0_sir, t_train, obs_train, GAMMA_FIXED)
    fix_res = evaluate(bc, gc, "fixed_gamma")
    print(f"  beta={bc:.4f}, gamma={gc:.4f} (fixat), R0={bc/gc:.2f}")
    print(f"  MAE_train={fix_res['mae_train']:.0f}, MAE_test={fix_res['mae_test']:.0f}")

    # CSV: ambele fituri suprapuse pe aceleasi zile
    sir_df = pd.DataFrame({
        "day": t_full.astype(int),
        "date": full["date"].dt.strftime("%Y-%m-%d"),
        "observed": obs_full.astype(int),
        "fit_free":  np.where(t_full < len(train), free_res["fit_full"], np.nan),
        "pred_free": np.where(t_full >= len(train), free_res["fit_full"], np.nan),
        "fit_fixed":  np.where(t_full < len(train), fix_res["fit_full"], np.nan),
        "pred_fixed": np.where(t_full >= len(train), fix_res["fit_full"], np.nan),
    })
    sir_df.to_csv(DATA_OUT / "calibration_sir_romania.csv", index=False)
    print(f"  -> {DATA_OUT.relative_to(REPO_ROOT)}/calibration_sir_romania.csv")

    # ---- Peisaj de pierdere 2D pentru identifiabilitate ----
    print("\n=== Identifiabilitate: grila 2D (beta, gamma) ===")
    grid = loss_grid(n, y0_sir, t_train, obs_train)
    print(f"  {len(grid)} puncte, MSE min={grid['mse'].min():.0f}, max={grid['mse'].max():.0f}")
    grid["log_mse"] = np.log10(grid["mse"].clip(lower=1))
    grid.to_csv(DATA_OUT / "identifiability_grid_sir.csv", index=False)
    print(f"  -> {DATA_OUT.relative_to(REPO_ROOT)}/identifiability_grid_sir.csv")

    # ---- Tabel LaTeX comparativ liber vs constrans ----
    table = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Calibrare SIR pe Romania, valul 1 ($15$~martie -- $15$~august 2020 antrenare, "
        r"$16$~august -- $15$~septembrie 2020 test). "
        r"Doua scenarii: \emph{liber} (optimizeaza ambele rate, $(\beta,\gamma)$), "
        r"\emph{constrans} (foloseste $\gamma=1/14$ din durata clinica medie a infectiei COVID-19, "
        r"optimizeaza doar $\beta$). Comparatia ilustreaza tensiunea dintre minimizarea pierderii "
        r"si interpretabilitatea epidemiologica a parametrilor.}",
        r"\label{tab:calibration_results}",
        r"\begin{tabularx}{\textwidth}{l r r X}",
        r"\toprule",
        r"\textbf{Marime} & \textbf{Liber} & \textbf{Constrans} & \textbf{Observatii} \\",
        r"\midrule",
        rf"$\hat{{\beta}}$ (zi$^{{-1}}$) & {free_res['beta']:.4f} & {fix_res['beta']:.4f} & rata de transmitere \\",
        rf"$\hat{{\gamma}}$ (zi$^{{-1}}$) & {free_res['gamma']:.4f} & {fix_res['gamma']:.4f} (\textit{{fix}}) & "
        rf"$1/\hat{{\gamma}}$ liber $= {1/free_res['gamma']:.1f}$ zile (non-fizic), constrans $= 14$ zile \\",
        rf"$\hat{{\mathcal{{R}}}}_0$ & {free_res['R0']:.2f} & {fix_res['R0']:.2f} & valori de literatura pentru tulpina originala $\sim 2$--$3$ \\",
        r"\midrule",
        rf"MAE antrenare & {free_res['mae_train']:.0f} & {fix_res['mae_train']:.0f} & cazuri \\",
        rf"RMSE antrenare & {free_res['rmse_train']:.0f} & {fix_res['rmse_train']:.0f} & cazuri \\",
        rf"MAE test & {free_res['mae_test']:.0f} & {fix_res['mae_test']:.0f} & extrapolare 1 luna \\",
        rf"RMSE test & {free_res['rmse_test']:.0f} & {fix_res['rmse_test']:.0f} & cazuri \\",
        r"\bottomrule",
        r"\end{tabularx}",
        r"\end{table*}",
    ]
    (TABLES_OUT / "calibration_results.tex").write_text("\n".join(table) + "\n")
    print(f"\n  -> {TABLES_OUT.relative_to(REPO_ROOT)}/calibration_results.tex")

    return 0


if __name__ == "__main__":
    sys.exit(main())
