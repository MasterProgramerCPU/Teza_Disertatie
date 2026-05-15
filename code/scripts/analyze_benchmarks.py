"""Analizeaza rezultatele unei campanii de benchmark si genereaza tabele LaTeX.

Citeste benchmark-urile direct din baza de date (presupune port-forward activ
catre yb-tserver pe portul local indicat) si scrie tabele LaTeX in directorul
``docs/tables/``, gata de \\input din capitolul de evaluare. Acopera atat
runnerele compartimentale (R/Julia/Python) cat si runner-ul LSTM dedicat.

Usage:
    # presupune port-forward: kubectl port-forward -n epimodel svc/yb-tserver-service 15433:5433
    python analyze_benchmarks.py --study <STUDY_ID> [--exclude <SIM_ID>...]

Tabelele generate (in docs/tables/):
    bench_wall_time.tex          - mediana wall-time per (model, limbaj, t_max)
    bench_speedup_vs_python.tex  - raport de viteza fata de Python
    bench_memory.tex             - memorie reziduala peak per limbaj
    bench_julia_coldstart.tex    - costul de pornire JIT pentru Julia
    bench_lstm.tex               - costul runner-ului LSTM
"""

from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLES_DIR = REPO_ROOT / "docs" / "tables"

T_MAXS = (90, 365, 2000, 10000)
MODELS = ("sis", "sir", "seir", "sirs", "sidarthe")
LANGS = ("r", "julia", "python")


def psql(query: str, host: str, port: int, user: str, dbname: str) -> list[list[str]]:
    cmd = ["psql", "-h", host, "-p", str(port), "-U", user, "-d", dbname,
           "-At", "-F", "|", "-c", query]
    env = {**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "yugabyte")}
    out = subprocess.check_output(cmd, env=env).decode()
    return [line.split("|") for line in out.strip().split("\n") if line]


def median(xs):
    return statistics.median(xs) if xs else 0.0


def fetch_ode(study: str, exclude: list[str], **db) -> dict:
    where_excl = " AND s.id NOT IN (" + ",".join(f"'{x}'" for x in exclude) + ")" if exclude else ""
    rows = psql(f"""
        SELECT s.model_type, s.language, s.t_max,
               b.wall_time_ms, b.cpu_time_ms, b.peak_memory_mb,
               s.created_at
        FROM benchmarks b
        JOIN simulation_runs s ON s.id = b.simulation_id
        WHERE s.study_id = '{study}' AND s.model_type != 'lstm'{where_excl}
        ORDER BY s.model_type, s.language, s.t_max, s.created_at;
    """, **db)
    groups = defaultdict(list)
    for r in rows:
        groups[(r[0], r[1], int(r[2]))].append(
            (float(r[3]), float(r[4]), float(r[5]), r[6])
        )
    return groups


def fetch_lstm(study: str, **db) -> dict:
    rows = psql(f"""
        SELECT s.t_max, b.wall_time_ms, b.cpu_time_ms, b.peak_memory_mb
        FROM benchmarks b JOIN simulation_runs s ON s.id = b.simulation_id
        WHERE s.study_id = '{study}' AND s.model_type = 'lstm'
        ORDER BY s.t_max, s.created_at;
    """, **db)
    groups = defaultdict(list)
    for r in rows:
        groups[int(r[0])].append((float(r[1]), float(r[2]), float(r[3])))
    return groups


def write_wall_time_table(groups: dict) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Wall-time median al solverului (ms), pe model si limbaj, pentru patru orizonturi $t_{\max}$. "
        r"Rezultate din campania de benchmark prin aplicatie (cluster \texttt{kube-4kdhb}, 3 worker x 4 vCPU / 8 GiB), "
        r"3 repetari per combinatie, dataset Romania OWID, prima inregistrare ca conditie initiala.}",
        r"\label{tab:bench_wall_time}",
        r"\small",
        r"\begin{tabularx}{\textwidth}{l l rrrr}",
        r"\toprule",
        r"\textbf{Model} & \textbf{Limbaj} & \multicolumn{4}{c}{\textbf{Wall-time median (ms)}} \\",
        r"\cmidrule(l){3-6}",
        r" & & $t_{\max}=90$ & $t_{\max}=365$ & $t_{\max}=2000$ & $t_{\max}=10000$ \\",
        r"\midrule",
    ]
    for i, model in enumerate(MODELS):
        for lang in LANGS:
            cells = []
            for tm in T_MAXS:
                walls = [v[0] for v in groups.get((model, lang, tm), [])]
                cells.append(f"{median(walls):.1f}" if walls else "--")
            lines.append(f"\\texttt{{{model}}} & \\texttt{{{lang}}} & " + " & ".join(cells) + r" \\")
        if i < len(MODELS) - 1:
            lines.append(r"\midrule")
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table*}"]
    (TABLES_DIR / "bench_wall_time.tex").write_text("\n".join(lines) + "\n")


def write_speedup_table(groups: dict) -> None:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Raport de viteza al solverului fata de Python (mediana wall-time Python / mediana limbaj). "
        r"Valori $>1$ inseamna mai rapid decat Python; valori $<1$ inseamna mai lent. "
        r"Pragul `$>x$' apare cand mediana sub-milisecundara face raportul exact instabil.}",
        r"\label{tab:bench_speedup_vs_python}",
        r"\small",
        r"\begin{tabularx}{\textwidth}{l l rrrr}",
        r"\toprule",
        r"\textbf{Model} & \textbf{Limbaj} & \multicolumn{4}{c}{\textbf{Speedup vs Python}} \\",
        r"\cmidrule(l){3-6}",
        r" & & $t_{\max}=90$ & $t_{\max}=365$ & $t_{\max}=2000$ & $t_{\max}=10000$ \\",
        r"\midrule",
    ]
    for i, model in enumerate(MODELS):
        py_meds = {tm: median([v[0] for v in groups.get((model, "python", tm), [])]) for tm in T_MAXS}
        for lang in ("r", "julia"):
            cells = []
            for tm in T_MAXS:
                walls = [v[0] for v in groups.get((model, lang, tm), [])]
                if not walls:
                    cells.append("--")
                    continue
                lang_med = median(walls)
                py_med = py_meds[tm]
                if lang_med < 0.5 and py_med >= 0.5:
                    cells.append(f"$>{py_med * 2:.0f}$")
                elif lang_med >= 0.5:
                    cells.append(f"{py_med / lang_med:.2f}")
                else:
                    cells.append("--")
            lines.append(f"\\texttt{{{model}}} & \\texttt{{{lang}}} & " + " & ".join(cells) + r" \\")
        if i < len(MODELS) - 1:
            lines.append(r"\midrule")
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table*}"]
    (TABLES_DIR / "bench_speedup_vs_python.tex").write_text("\n".join(lines) + "\n")


def write_memory_table(groups: dict) -> None:
    descs = {
        "r": "interpretat, pachete deSolve+RPostgres incarcate",
        "julia": "JIT, runtime DifferentialEquations.jl",
        "python": "interpretat, NumPy+SciPy",
    }
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Memorie reziduala peak (MB), mediana pe toate combinatiile model x $t_{\max}$.}",
        r"\label{tab:bench_memory}",
        r"\begin{tabularx}{\columnwidth}{l X r}",
        r"\toprule",
        r"\textbf{Limbaj} & \textbf{Caracteristica runtime} & \textbf{Memorie median (MB)} \\",
        r"\midrule",
    ]
    for lang in LANGS:
        all_mems = [v[2] for model in MODELS for tm in T_MAXS for v in groups.get((model, lang, tm), [])]
        lines.append(f"\\texttt{{{lang}}} & {descs[lang]} & {median(all_mems):.0f} \\\\")
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    (TABLES_DIR / "bench_memory.tex").write_text("\n".join(lines) + "\n")


def write_coldstart_table(groups: dict) -> None:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Costul de pornire JIT pentru runner-ul Julia: prima rulare include compilarea, "
        r"repetarile ulterioare ruleaza din cod cache-uit. Valori la $t_{\max}=90$.}",
        r"\label{tab:bench_julia_coldstart}",
        r"\begin{tabularx}{\columnwidth}{l r r r}",
        r"\toprule",
        r"\textbf{Model} & \textbf{Rep 1 (ms)} & \textbf{Mediana rep 2-3 (ms)} & \textbf{Cost JIT (ms)} \\",
        r"\midrule",
    ]
    for model in MODELS:
        runs = sorted(groups.get((model, "julia", 90), []), key=lambda v: v[3])
        if len(runs) >= 3:
            first = runs[0][0]
            warm = median([v[0] for v in runs[1:]])
            lines.append(f"\\texttt{{{model}}} & {first:.0f} & {warm:.0f} & {first - warm:.0f} \\\\")
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    (TABLES_DIR / "bench_julia_coldstart.tex").write_text("\n".join(lines) + "\n")


def write_lstm_table(lstm_groups: dict) -> None:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Costul rularii pentru runner-ul LSTM dedicat (Python, hand-rolled NumPy), parametri impliciti "
        r"(\texttt{lookback=14}, \texttt{hidden\_size=12}, \texttt{epochs=150}, \texttt{learning\_rate=0.01}), "
        r"dataset Romania OWID (1\,440 zile, $80\%$ antrenare / $20\%$ test cronologic). "
        r"Forecast-ul autoregresiv pe orizontul $t_{\max}$ are cost neglijabil fata de antrenare.}",
        r"\label{tab:bench_lstm}",
        r"\begin{tabularx}{\columnwidth}{r r r r r}",
        r"\toprule",
        r"$t_{\max}$ & \textbf{n} & \textbf{Wall median (s)} & \textbf{CPU median (s)} & \textbf{Memorie (MB)} \\",
        r"\midrule",
    ]
    for tm in sorted(lstm_groups):
        walls = [v[0] / 1000 for v in lstm_groups[tm]]
        cpus = [v[1] / 1000 for v in lstm_groups[tm]]
        mems = [v[2] for v in lstm_groups[tm]]
        lines.append(f"{tm} & {len(walls)} & {median(walls):.1f} & {median(cpus):.1f} & {median(mems):.1f} \\\\")
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    (TABLES_DIR / "bench_lstm.tex").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Genereaza tabelele LaTeX din rezultatele campaniei.")
    p.add_argument("--study", required=True, help="UUID-ul studiului de benchmark")
    p.add_argument("--exclude", action="append", default=[], help="ID-uri de simulari de exclus (smoke test etc.)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=15433)
    p.add_argument("--user", default="yugabyte")
    p.add_argument("--dbname", default="yugabyte")
    args = p.parse_args(argv)

    db = dict(host=args.host, port=args.port, user=args.user, dbname=args.dbname)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    ode_groups = fetch_ode(args.study, args.exclude, **db)
    lstm_groups = fetch_lstm(args.study, **db)

    write_wall_time_table(ode_groups)
    write_speedup_table(ode_groups)
    write_memory_table(ode_groups)
    write_coldstart_table(ode_groups)
    write_lstm_table(lstm_groups)

    print(f"Scrise 5 tabele in {TABLES_DIR.relative_to(REPO_ROOT)}/")
    print(f"  ODE: {sum(len(v) for v in ode_groups.values())} rulari in {len(ode_groups)} combinatii")
    print(f"  LSTM: {sum(len(v) for v in lstm_groups.values())} rulari in {len(lstm_groups)} orizonturi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
