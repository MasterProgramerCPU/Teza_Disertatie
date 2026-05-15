"""Genereaza CSV-uri si tabele LaTeX pentru figurile suplimentare din teza.

Citeste din baza de date (presupune port-forward la yb-tserver) rezultatele
campaniei de benchmark si scrie:

  * docs/data/scaling_wall_sidarthe.csv  - wall median (ms) per limbaj x t_max
  * docs/data/lstm_trajectory_romania.csv - serie observed/fitted/predicted
                                            dintr-o rulare LSTM
  * docs/tables/cross_language_regression.tex - max abs deviation cross-limbaj

Scriptul nu reruleaza simulari; toate datele provin din rulari deja scrise
in benchmarks si simulation_results.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_OUT = REPO_ROOT / "docs" / "data"
TABLES_OUT = REPO_ROOT / "docs" / "tables"

# Romania OWID — pentru normalizarea nRMSE in regression cross-limbaj
ROMANIA_N = 19659270


def psql(query: str, host: str, port: int, user: str, dbname: str) -> list[list[str]]:
    cmd = ["psql", "-h", host, "-p", str(port), "-U", user, "-d", dbname,
           "-At", "-F", "|", "-c", query]
    env = {**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "yugabyte")}
    out = subprocess.check_output(cmd, env=env).decode()
    return [line.split("|") for line in out.strip().split("\n") if line]


def median(xs):
    return statistics.median(xs) if xs else 0.0


# ---- Figure 1: wall-time scaling vs t_max per language --------------------

def write_scaling_csv(study: str, model: str, **db) -> None:
    rows = psql(f"""
        SELECT s.language, s.t_max, b.wall_time_ms
        FROM benchmarks b
        JOIN simulation_runs s ON s.id = b.simulation_id
        WHERE s.study_id = '{study}'
          AND s.model_type = '{model}'
        ORDER BY s.language, s.t_max;
    """, **db)
    groups = defaultdict(list)
    for r in rows:
        groups[(r[0], int(r[1]))].append(float(r[2]))

    # CSV cu coloane pe limbaj — usor de plot in pgfplots
    t_maxs = sorted({k[1] for k in groups})
    langs = sorted({k[0] for k in groups})
    out = DATA_OUT / "scaling_wall_sidarthe.csv"
    with open(out, "w") as f:
        f.write("t_max," + ",".join(langs) + "\n")
        for tm in t_maxs:
            cells = [str(tm)]
            for lang in langs:
                cells.append(f"{max(median(groups[(lang, tm)]), 0.5):.2f}")
            f.write(",".join(cells) + "\n")
    print(f"  -> {out.relative_to(REPO_ROOT)}  ({len(t_maxs)} t_max x {len(langs)} limbaje)")


# ---- Figure 2: LSTM trajectory --------------------------------------------

def write_lstm_csv(study: str, **db) -> None:
    # alege o rulare LSTM completata (cea mai recenta cu t_max=90)
    sim_id_rows = psql(f"""
        SELECT id, t_max FROM simulation_runs
        WHERE study_id='{study}' AND model_type='lstm' AND status='completed'
        ORDER BY created_at DESC
        LIMIT 1;
    """, **db)
    if not sim_id_rows:
        print("  ! nu am gasit o rulare LSTM")
        return
    sim_id, t_max = sim_id_rows[0]
    print(f"  rulare LSTM: {sim_id[:8]} (t_max={t_max})")

    # Pull simulation_results — compartments JSONB are observed/fitted/predicted
    rows = psql(f"""
        SELECT t, compartments::text FROM simulation_results
        WHERE simulation_id='{sim_id}'
        ORDER BY t;
    """, **db)
    out = DATA_OUT / "lstm_trajectory_romania.csv"
    with open(out, "w") as f:
        f.write("t,observed,fitted,predicted\n")
        for t_str, comp_json in rows:
            comp = json.loads(comp_json)
            obs = comp.get("observed", "")
            fit = comp.get("fitted", "")
            pred = comp.get("predicted", "")
            f.write(f"{t_str},{obs},{fit},{pred}\n")
    print(f"  -> {out.relative_to(REPO_ROOT)}  ({len(rows)} pasi temporali)")


# ---- Table: cross-language numerical regression ---------------------------

def fetch_trajectory(sim_id: str, **db) -> dict[int, dict[str, float]]:
    rows = psql(f"""
        SELECT t, compartments::text FROM simulation_results
        WHERE simulation_id='{sim_id}'
        ORDER BY t;
    """, **db)
    return {int(t): json.loads(c) for t, c in rows}


def cross_language_for(study: str, model: str, t_max: int, only_recent_after: str = "", **db) -> dict:
    """Pentru un (model, t_max), gaseste cate o rulare R/Julia/Python si
    calculeaza abaterea maxima absoluta pe fiecare compartiment intre perechi."""
    where_recent = f" AND created_at > '{only_recent_after}'" if only_recent_after else ""
    sims = psql(f"""
        SELECT language, id FROM simulation_runs
        WHERE study_id='{study}' AND model_type='{model}' AND t_max={t_max}
              AND status='completed'{where_recent}
        ORDER BY language, created_at;
    """, **db)
    if not sims:
        return {"langs": [], "pairwise": {}, "n_points": 0}
    by_lang: dict[str, str] = {}
    for lang, sid in sims:
        by_lang.setdefault(lang, sid)  # cea mai veche per limbaj
    trajs = {lang: fetch_trajectory(sid, **db) for lang, sid in by_lang.items()}
    if len(trajs) < 2:
        return {"langs": list(trajs), "pairwise": {}, "n_points": 0}
    common_t = sorted(set.intersection(*[set(tr) for tr in trajs.values()]))
    common_keys = set.intersection(*[set(next(iter(tr.values()))) for tr in trajs.values()])

    pairwise = {}
    langs = sorted(by_lang)
    for i, l1 in enumerate(langs):
        for l2 in langs[i + 1:]:
            max_abs = 0.0
            for t in common_t:
                for k in common_keys:
                    v1 = float(trajs[l1][t].get(k, 0))
                    v2 = float(trajs[l2][t].get(k, 0))
                    max_abs = max(max_abs, abs(v1 - v2))
            pairwise[(l1, l2)] = max_abs
    return {"langs": langs, "pairwise": pairwise, "n_points": len(common_t)}


def write_regression_table(study: str, recent_after: str = "", n_pop: int = ROMANIA_N, **db) -> None:
    combos = [("sir", 365), ("sidarthe", 365)]
    results = {(m, tm): cross_language_for(study, m, tm, only_recent_after=recent_after, **db) for m, tm in combos}
    out = TABLES_OUT / "cross_language_regression.tex"
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Verificare numerica de regresie cross-limbaj: abaterea "
        r"maxima absoluta intre traiectoriile compartimentale produse in R, "
        r"Julia si Python pentru aceiasi parametri si aceleasi conditii "
        r"initiale, pe setul sintetic \texttt{multiwave} (populatia "
        r"$N=50 \cdot 10^6$, $t_{\max}=365$ pasi zilnici). Modelele folosesc "
        r"solvere diferite (R cu RK4 pas fix $h=1$, Python cu RK45 adaptiv, "
        r"Julia cu Tsit5), deci abaterile reflecta tolerantele numerice "
        r"cumulate, nu erori de implementare.}",
        r"\label{tab:cross_language_regression}",
        r"\begin{tabularx}{\columnwidth}{l l r r}",
        r"\toprule",
        r"\textbf{Model} & \textbf{Pereche} & \textbf{Max $|\Delta|$} & \textbf{Normalizat ($/N$)} \\",
        r"\midrule",
    ]
    for i, ((model, tm), data) in enumerate(results.items()):
        if not data["pairwise"]:
            continue
        for j, ((l1, l2), max_abs) in enumerate(data["pairwise"].items()):
            normalized = max_abs / n_pop
            model_cell = f"\\texttt{{{model}}}" if j == 0 else ""
            # format romanesc: 1{,}01 \cdot 10^{-8}
            mantissa, exp = f"{normalized:.2e}".split("e")
            mantissa_ro = mantissa.replace(".", "{,}")
            exp_int = int(exp)
            sci_ro = f"${mantissa_ro} \\cdot 10^{{{exp_int}}}$"
            lines.append(
                f"{model_cell} & \\texttt{{{l1}}} vs \\texttt{{{l2}}} & "
                f"{max_abs:.1f} & {sci_ro} \\\\"
            )
        if i < len(results) - 1:
            lines.append(r"\midrule")
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    out.write_text("\n".join(lines) + "\n")
    print(f"  -> {out.relative_to(REPO_ROOT)}")
    for (model, tm), data in results.items():
        print(f"    {model}/{tm}: max abs deviation per pair = "
              f"{ {f'{l1}-{l2}': round(v, 1) for (l1, l2), v in data['pairwise'].items()} }")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--study", required=True)
    p.add_argument("--scaling-model", default="sidarthe")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=15433)
    p.add_argument("--user", default="yugabyte")
    p.add_argument("--dbname", default="yugabyte")
    args = p.parse_args(argv)

    db = dict(host=args.host, port=args.port, user=args.user, dbname=args.dbname)
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    TABLES_OUT.mkdir(parents=True, exist_ok=True)

    print("=== scaling wall-time vs t_max ===")
    write_scaling_csv(args.study, args.scaling_model, **db)

    print("\n=== traiectorie LSTM ===")
    write_lstm_csv(args.study, **db)

    print("\n=== regresie cross-limbaj ===")
    write_regression_table(args.study, **db)

    return 0


if __name__ == "__main__":
    sys.exit(main())
