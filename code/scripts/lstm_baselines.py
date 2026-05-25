"""Validarea LSTM fata de predictori naivi (baseline-uri) pe fereastra de test.

Capitolul de predictie raporteaza ca runner-ul LSTM produce predictii o-zi-inainte
care urmaresc seria observata. O intrebare de rigoare este insa: \\emph{bate} LSTM-ul
predictori triviali? In prognoza de serii temporale, baseline-ul de persistenta
($\\hat{y}_t = y_{t-1}$) este notoriu de greu de batut pentru serii netede.

Acest script compara, pe aceeasi fereastra de test (ultimele $20\\%$ din seria
Romania), eroarea o-zi-inainte a LSTM-ului cu trei baseline-uri:
  * \\emph{persistenta}     --- $\\hat{y}_t = y_{t-1}$;
  * \\emph{drift}           --- extrapolare cu ultima diferenta, $\\hat{y}_t = 2y_{t-1} - y_{t-2}$;
  * \\emph{medie mobila 7}  --- $\\hat{y}_t = \\frac{1}{7}\\sum_{k=1}^{7} y_{t-k}$.

Toate predictiile baseline folosesc doar valori observate trecute, exact ca LSTM-ul.
Se raporteaza si \\emph{scorul de pricepere} (skill) fata de persistenta, plus
fractiunea de zile ``plate'' din fereastra de test, care explica de ce persistenta
este atat de competitiva pe date cu cadenta de raportare saptamanala.

Lucreaza direct pe \\texttt{docs/data/lstm\\_trajectory\\_romania.csv} (produs de
\\texttt{generate\\_figures.py}), deci nu necesita acces la cluster.

Output:
    docs/data/lstm_baselines.csv
    docs/tables/lstm_baselines.tex
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_IN = REPO_ROOT / "docs" / "data" / "lstm_trajectory_romania.csv"
DATA_OUT = REPO_ROOT / "docs" / "data" / "lstm_baselines.csv"
TBL_OUT = REPO_ROOT / "docs" / "tables" / "lstm_baselines.tex"

# Granita antrenare/test: 80% din cele 1440 de puncte observate (vezi figura LSTM).
TEST_START = 1152
TEST_END = 1439


def mae(pred: dict[int, float], obs: dict[int, float]) -> float:
    e = [abs(pred[t] - obs[t]) for t in pred]
    return sum(e) / len(e)


def rmse(pred: dict[int, float], obs: dict[int, float]) -> float:
    e = [(pred[t] - obs[t]) ** 2 for t in pred]
    return math.sqrt(sum(e) / len(e))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validare LSTM vs baseline-uri naive.")
    p.add_argument("--input", default=str(CSV_IN))
    p.add_argument("--test-start", type=int, default=TEST_START)
    p.add_argument("--test-end", type=int, default=TEST_END)
    args = p.parse_args(argv)

    rows = list(csv.DictReader(open(args.input)))
    obs = {int(r["t"]): float(r["observed"]) for r in rows if r["observed"] != ""}
    fit = {int(r["t"]): float(r["fitted"]) for r in rows if r["fitted"] != ""}

    test_t = [t for t in range(args.test_start, args.test_end + 1) if t in obs]

    lstm = {t: fit[t] for t in test_t if t in fit}
    persistence = {t: obs[t - 1] for t in test_t if t - 1 in obs}
    drift = {t: 2 * obs[t - 1] - obs[t - 2] for t in test_t if t - 1 in obs and t - 2 in obs}
    ma7 = {t: sum(obs[t - k] for k in range(1, 8)) / 7
           for t in test_t if all(t - k in obs for k in range(1, 8))}

    methods = [
        ("LSTM (o-zi-înainte)", lstm),
        ("Persistență", persistence),
        ("Drift (ultima diferență)", drift),
        ("Medie mobilă (7 zile)", ma7),
    ]
    mae_pers = mae(persistence, obs)

    # cadenta de raportare: fractiunea de zile plate (obs[t]==obs[t-1])
    cmp_t = [t for t in test_t if t - 1 in obs]
    flat = sum(1 for t in cmp_t if obs[t] == obs[t - 1])
    flat_pct = 100.0 * flat / len(cmp_t)

    print(f"Fereastra de test: t={args.test_start}..{args.test_end}  "
          f"({len(test_t)} zile)")
    print(f"Zile 'plate' (raportare neactualizata): {flat}/{len(cmp_t)} "
          f"({flat_pct:.0f}%)\n")
    print(f"{'Metoda':26s} {'n':>4} {'MAE':>9} {'RMSE':>9} {'skill MAE':>10}")
    results = []
    for name, pred in methods:
        m, r = mae(pred, obs), rmse(pred, obs)
        skill = (1 - m / mae_pers) * 100.0
        results.append((name, len(pred), m, r, skill))
        print(f"{name:26s} {len(pred):>4} {m:>9.1f} {r:>9.1f} {skill:>9.1f}%")

    # CSV
    with open(DATA_OUT, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["method", "n", "mae", "rmse", "skill_vs_persistence_pct"])
        for name, n, m, r, s in results:
            w.writerow([name, n, round(m, 2), round(r, 2), round(s, 1)])
    print(f"\n-> {DATA_OUT.relative_to(REPO_ROOT)}")

    # Tabel LaTeX
    lines = [
        r"\begin{table}[!htbp]",
        r"\centering",
        rf"\caption{{Validarea LSTM fata de predictori naivi, eroare o-zi-inainte pe "
        rf"fereastra de test (ultimele $20\%$ din seria Romania, ${len(test_t)}$ zile). "
        r"Toate metodele folosesc doar valori observate trecute. \emph{Skill} este "
        r"reducerea relativa a MAE fata de persistenta (valori negative = mai slab decat "
        rf"persistenta). Pe aceasta serie, ${flat_pct:.0f}\%$ din zilele de test sunt "
        r"identice cu ziua precedenta (raportare saptamanala), ceea ce face persistenta "
        r"extrem de greu de batut.}",
        r"\label{tab:lstm_baselines}",
        r"\small",
        r"\begin{tabularx}{\columnwidth}{X r r r}",
        r"\toprule",
        r"\textbf{Metodă} & \textbf{MAE} & \textbf{RMSE} & \textbf{Skill} \\",
        r"\midrule",
    ]
    for name, n, m, r, s in results:
        skill_cell = "---" if abs(s) < 1e-9 else f"{s:+.0f}\\%"
        lines.append(f"{name} & {m:.0f} & {r:.0f} & {skill_cell} \\\\")
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    TBL_OUT.write_text("\n".join(lines) + "\n")
    print(f"-> {TBL_OUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
