"""Compara timings cluster (DB) vs local M1 (CSV) si genereaza tabel + figura.

Foloseste:
  - rezultatele cluster din tabela `benchmarks` (Python, study Benchmark sintetic),
    pentru workload-ul synthetic_multiwave (I0=100, non-trivial);
  - rezultatele M1 native din \\texttt{docs/data/bench\\_local\\_m1.csv}.

Output:
  - docs/tables/hardware_comparison.tex
  - docs/data/hardware_compare.csv (cluster_wall, m1_wall, ratio per combo)
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTH_STUDY = Path("/tmp/synth_study.txt").read_text().strip()
M1_CSV = REPO_ROOT / "docs" / "data" / "bench_local_m1.csv"
OUT_TBL = REPO_ROOT / "docs" / "tables" / "hardware_comparison.tex"
OUT_CSV = REPO_ROOT / "docs" / "data" / "hardware_compare.csv"


def psql(query: str) -> list[list[str]]:
    cmd = ["psql", "-h", "127.0.0.1", "-p", "15433", "-U", "yugabyte", "-d", "yugabyte",
           "-At", "-F", "|", "-c", query]
    env = {**os.environ, "PGPASSWORD": "yugabyte"}
    return [l.split("|") for l in subprocess.check_output(cmd, env=env).decode().strip().split("\n") if l]


def median(xs): return sorted(xs)[len(xs) // 2] if xs else 0.0


# 1. cluster timings per (model, t_max) — pe sintetic, Python
cluster_rows = psql(f"""
    SELECT s.model_type, s.t_max, b.wall_time_ms
    FROM benchmarks b JOIN simulation_runs s ON s.id = b.simulation_id
    WHERE s.study_id = '{SYNTH_STUDY}' AND s.language = 'python'
    ORDER BY s.model_type, s.t_max;
""")
cluster_groups = defaultdict(list)
for r in cluster_rows:
    cluster_groups[(r[0], int(r[1]))].append(float(r[2]))

# 2. M1 timings per (model, t_max) — pe synthetic only
m1_groups = defaultdict(list)
with open(M1_CSV) as f:
    for r in csv.DictReader(f):
        if r["workload"] == "synthetic":
            m1_groups[(r["model"], int(r["t_max"]))].append(float(r["wall_ms"]))

# 3. side-by-side
print(f"{'model':10s} {'t_max':>6} {'n_cluster':>9} {'cluster (ms)':>13} "
      f"{'n_m1':>5} {'M1 (ms)':>10} {'speedup M1':>11}")
combos = sorted(set(cluster_groups) & set(m1_groups))
rows = []
for k in combos:
    cm = median(cluster_groups[k])
    mm = median(m1_groups[k])
    ratio = cm / mm if mm > 0 else 0
    nc = len(cluster_groups[k])
    nm = len(m1_groups[k])
    rows.append({"model": k[0], "t_max": k[1], "cluster_n": nc, "cluster_wall_med_ms": cm,
                 "m1_n": nm, "m1_wall_med_ms": mm, "speedup": ratio})
    print(f"{k[0]:10s} {k[1]:>6} {nc:>9} {cm:>13.1f} {nm:>5} {mm:>10.2f} {ratio:>10.1f}x")

# 4. write CSV
with open(OUT_CSV, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(f"\n-> {OUT_CSV.relative_to(REPO_ROOT)}")

# 5. LaTeX table
lines = [
    r"\begin{table*}[!htbp]",
    r"\centering",
    r"\caption{Comparatia timpilor de executie pentru solverul Python (\texttt{scipy.solve\_ivp} RK45) "
    r"pe doua profile hardware distincte: cluster \texttt{kube-4kdhb} (worker amd64, OpenStack VM, "
    r"4 vCPU / 8 GiB, runner in container, wall-time include si scrierea rezultatelor in YugabyteDB) "
    r"vs M1 Pro arm64 nativ (script standalone, fara container, fara DB). "
    r"Workload non-trivial: set sintetic \texttt{multiwave} cu $I_0 = 100$, $N = 5 \cdot 10^7$. "
    r"Coloana \emph{speedup M1} este raportul medianelor; valori $>1$ inseamna M1 mai rapid.}",
    r"\label{tab:hardware_comparison}",
    r"\begin{tabularx}{\textwidth}{l r r r r r r}",
    r"\toprule",
    r"\textbf{Model} & \textbf{$t_{\max}$} & "
    r"\textbf{$n_{\mathrm{cluster}}$} & \textbf{Cluster wall (ms)} & "
    r"\textbf{$n_{\mathrm{M1}}$} & \textbf{M1 wall (ms)} & "
    r"\textbf{Speedup M1} \\",
    r"\midrule",
]
prev_model = None
for r in rows:
    model_cell = f"\\texttt{{{r['model']}}}" if r['model'] != prev_model else ""
    prev_model = r['model']
    lines.append(
        f"{model_cell} & {r['t_max']} & "
        f"{r['cluster_n']} & {r['cluster_wall_med_ms']:.1f} & "
        f"{r['m1_n']} & {r['m1_wall_med_ms']:.2f} & "
        f"{r['speedup']:.1f}$\\times$ \\\\"
    )
lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table*}"]
OUT_TBL.write_text("\n".join(lines) + "\n")
print(f"-> {OUT_TBL.relative_to(REPO_ROOT)}")
