"""Benchmark al API-ului si al transportului de date catre frontend.

Completeaza campania de benchmark numeric (care masoara doar solver-ul) cu
masuratori ale celor patru operatii expuse de API si percepute direct de
utilizator:

  * \\emph{create}  --- crearea unei simulari (validare input, citirea primului
    rand epidemiologic, inserare in \\texttt{simulation\\_runs}, publicare in
    coada Redis); raspunde asincron, inainte ca solver-ul sa ruleze;
  * \\emph{status}  --- interogarea starii unei simulari (o citire indexata);
  * \\emph{results} --- citirea traiectoriei complete (deserializare JSONB,
    construirea raspunsului JSON); creste cu numarul de puncte si cu numarul de
    compartimente ale modelului;
  * \\emph{export}  --- exportul CSV al aceleiasi traiectorii.

Pentru fiecare endpoint se raporteaza latenta mediana si percentila 95, plus
dimensiunea raspunsului. Spre deosebire de wall-time-ul solver-ului (masurat in
runner), aceste latente includ tot lantul HTTP -> API -> YugabyteDB -> HTTP,
deci arata daca limita sistemului este solver-ul, baza de date sau transportul.

Masuratorile sunt facute prin port-forward catre serviciul \\texttt{api} din
clusterul \\texttt{kube-4kdhb}, deci reflecta acelasi profil hardware ca restul
campaniei.

Exemplu:
    python bench_api.py \\
        --api-url http://localhost:8080 \\
        --email tudor@test.ro --password parola1234 \\
        --study <STUDY_ID> --dataset <DATASET_ID> \\
        --points 30 90 180 365 \\
        --create-repeat 12 --read-repeat 30 \\
        --output ../../docs/data/bench_api.csv
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
ODE_MODELS = ("sir", "sis", "seir", "sirs", "sidarthe")
POLL_INTERVAL_SEC = 0.5
POLL_TIMEOUT_SEC = 120.0


class APIError(RuntimeError):
    pass


class Client:
    """Invelis subtire peste API-ul aplicatiei, cu masurare de latenta."""

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _data(self, resp: requests.Response) -> dict:
        try:
            body = resp.json()
        except ValueError:
            raise APIError(f"raspuns non-JSON ({resp.status_code}) de la {resp.url}")
        if resp.status_code >= 400 or (isinstance(body, dict) and "error" in body):
            msg = body.get("error", {}).get("message", resp.text) if isinstance(body, dict) else resp.text
            raise APIError(f"{resp.status_code}: {msg}")
        return body.get("data", {})

    def login(self, email: str, password: str) -> None:
        resp = self.session.post(
            f"{self.base}/api/auth/login",
            json={"email": email, "password": password}, timeout=self.timeout,
        )
        token = self._data(resp).get("token")
        if not token:
            raise APIError("login a reusit dar nu a returnat token")
        self.session.headers["Authorization"] = f"Bearer {token}"

    def timed_create(self, study: str, dataset: str, model: str, t_max: int) -> tuple[float, str]:
        """Returneaza (latenta_ms, run_id) pentru POST de creare simulare."""
        t0 = time.perf_counter()
        resp = self.session.post(
            f"{self.base}/api/studies/{study}/simulations",
            json={"dataset_id": dataset, "model_type": model,
                  "language": "python", "t_max": t_max},
            timeout=self.timeout,
        )
        latency = (time.perf_counter() - t0) * 1000.0
        run_id = self._data(resp).get("id")
        if not run_id:
            raise APIError("crearea simularii nu a returnat un id")
        return latency, run_id

    def timed_get(self, path: str) -> tuple[float, int]:
        """Returneaza (latenta_ms, bytes) pentru un GET pe un endpoint."""
        t0 = time.perf_counter()
        resp = self.session.get(f"{self.base}{path}", timeout=self.timeout)
        latency = (time.perf_counter() - t0) * 1000.0
        if resp.status_code >= 400:
            raise APIError(f"{resp.status_code} la {path}")
        return latency, len(resp.content)

    def wait_completed(self, study: str, run_id: str) -> str:
        deadline = time.perf_counter() + POLL_TIMEOUT_SEC
        while True:
            data = self._data(self.session.get(
                f"{self.base}/api/studies/{study}/simulations/{run_id}", timeout=self.timeout))
            status = data.get("status", "unknown")
            if status in ("completed", "failed"):
                return status
            if time.perf_counter() > deadline:
                return "timeout"
            time.sleep(POLL_INTERVAL_SEC)


def p50(xs): return statistics.median(xs) if xs else 0.0
def p95(xs):
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, int(round(0.95 * (len(s) - 1))))
    return s[k]


def measure_model(client: Client, study: str, dataset: str, model: str,
                  points: list[int], create_repeat: int, read_repeat: int) -> list[dict]:
    """Masoara toate cele patru endpointuri pentru un model, pe toate orizonturile."""
    rows: list[dict] = []
    ref = max(points)

    # ---- create latency: create_repeat POST-uri la orizontul de referinta ----
    create_lat: list[float] = []
    ids: list[str] = []
    for _ in range(create_repeat):
        lat, rid = client.timed_create(study, dataset, model, ref)
        create_lat.append(lat)
        ids.append(rid)

    # tinta de citit: prima simulare creata, dupa finalizare
    target_ref = ids[0]
    if client.wait_completed(study, target_ref) != "completed":
        raise APIError(f"simularea de referinta {model}/{ref} nu s-a finalizat")

    # ---- status latency pe simularea de referinta ----
    status_lat = [client.timed_get(
        f"/api/studies/{study}/simulations/{target_ref}")[0] for _ in range(read_repeat)]

    rows.append({"model": model, "points": ref, "endpoint": "create",
                 "p50_ms": p50(create_lat), "p95_ms": p95(create_lat),
                 "bytes": 0, "n": len(create_lat)})
    rows.append({"model": model, "points": ref, "endpoint": "status",
                 "p50_ms": p50(status_lat), "p95_ms": p95(status_lat),
                 "bytes": 0, "n": len(status_lat)})

    # ---- results + export pe fiecare orizont ----
    for pts in points:
        if pts == ref:
            rid = target_ref
        else:
            _, rid = client.timed_create(study, dataset, model, pts)
            if client.wait_completed(study, rid) != "completed":
                raise APIError(f"simularea {model}/{pts} nu s-a finalizat")

        res = [client.timed_get(f"/api/studies/{study}/simulations/{rid}/results")
               for _ in range(read_repeat)]
        exp = [client.timed_get(f"/api/studies/{study}/simulations/{rid}/export")
               for _ in range(read_repeat)]
        res_lat = [x[0] for x in res]
        exp_lat = [x[0] for x in exp]
        rows.append({"model": model, "points": pts, "endpoint": "results",
                     "p50_ms": p50(res_lat), "p95_ms": p95(res_lat),
                     "bytes": p50([x[1] for x in res]), "n": read_repeat})
        rows.append({"model": model, "points": pts, "endpoint": "export",
                     "p50_ms": p50(exp_lat), "p95_ms": p95(exp_lat),
                     "bytes": p50([x[1] for x in exp]), "n": read_repeat})

    return rows


# ---- generare tabele LaTeX -------------------------------------------------

def cell(rows, model, points, endpoint, field):
    for r in rows:
        if r["model"] == model and r["points"] == points and r["endpoint"] == endpoint:
            return r[field]
    return 0.0


def write_table_per_model(rows, out_path: Path, models: Sequence[str], ref: int) -> None:
    """Tabel per model, la orizontul de referinta (ref puncte)."""
    lines = [
        r"\begin{table*}[!htbp]",
        r"\centering",
        rf"\caption{{Latenta API pe model, la orizontul de $\,{ref}\,$ puncte (1 an, pas zilnic). "
        r"Pentru fiecare endpoint se raporteaza mediana ($p_{50}$); pentru \emph{results}, "
        r"endpointul cel mai greu, se raporteaza si percentila 95 ($p_{95}$) si dimensiunea "
        r"raspunsului JSON. \emph{create} raspunde asincron (inainte de rularea solver-ului); "
        r"\emph{results} si \emph{export} includ deserializarea din YugabyteDB. "
        r"Masurat prin port-forward la clusterul \texttt{kube-4kdhb}.}",
        r"\label{tab:api_latency}",
        r"\small",
        r"\begin{tabularx}{\textwidth}{l r r r r r r}",
        r"\toprule",
        r"\textbf{Model} & \textbf{Create} & \textbf{Status} & "
        r"\textbf{Results $p_{50}$} & \textbf{Results $p_{95}$} & "
        r"\textbf{JSON} & \textbf{Export} \\",
        r" & (ms) & (ms) & (ms) & (ms) & (KB) & (ms) \\",
        r"\midrule",
    ]
    for m in models:
        kb = cell(rows, m, ref, "results", "bytes") / 1024.0
        lines.append(
            f"\\texttt{{{m}}} & "
            f"{cell(rows, m, ref, 'create', 'p50_ms'):.1f} & "
            f"{cell(rows, m, ref, 'status', 'p50_ms'):.1f} & "
            f"{cell(rows, m, ref, 'results', 'p50_ms'):.1f} & "
            f"{cell(rows, m, ref, 'results', 'p95_ms'):.1f} & "
            f"{kb:.1f} & "
            f"{cell(rows, m, ref, 'export', 'p50_ms'):.1f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table*}"]
    out_path.write_text("\n".join(lines) + "\n")


def write_table_scaling(rows, out_path: Path, model: str, points: list[int]) -> None:
    """Tabel de scalare cu orizontul pentru un singur model (cel mai greu)."""
    lines = [
        r"\begin{table}[!htbp]",
        r"\centering",
        rf"\caption{{Scalarea latentei de citire cu orizontul, pentru modelul "
        rf"\texttt{{{model}}} ($8$ compartimente). Pe masura ce numarul de puncte creste, "
        r"latenta \emph{results} si dimensiunea JSON cresc aproximativ liniar, in timp ce "
        r"\emph{export} CSV ramane mai ieftin (text plat, fara structura JSON).}",
        rf"\label{{tab:api_latency_scaling}}",
        r"\small",
        r"\begin{tabularx}{\columnwidth}{r r r r r}",
        r"\toprule",
        r"\textbf{Puncte} & \textbf{Results $p_{50}$} & \textbf{Results $p_{95}$} & "
        r"\textbf{JSON} & \textbf{Export} \\",
        r" & (ms) & (ms) & (KB) & (ms) \\",
        r"\midrule",
    ]
    for pts in points:
        kb = cell(rows, model, pts, "results", "bytes") / 1024.0
        lines.append(
            f"{pts} & "
            f"{cell(rows, model, pts, 'results', 'p50_ms'):.1f} & "
            f"{cell(rows, model, pts, 'results', 'p95_ms'):.1f} & "
            f"{kb:.1f} & "
            f"{cell(rows, model, pts, 'export', 'p50_ms'):.1f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabularx}", r"\end{table}"]
    out_path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Benchmark al API-ului si transportului de date.")
    p.add_argument("--api-url", default="http://localhost:8080")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--study", required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--model", action="append", default=None,
                   help=f"model de testat (repetabil); implicit toate: {', '.join(ODE_MODELS)}")
    p.add_argument("--points", type=int, nargs="+", default=[30, 90, 180, 365],
                   help="numar de puncte (= t_max) de baleiat (implicit 30 90 180 365)")
    p.add_argument("--create-repeat", type=int, default=12)
    p.add_argument("--read-repeat", type=int, default=30)
    p.add_argument("--output", default=str(REPO_ROOT / "docs" / "data" / "bench_api.csv"))
    p.add_argument("--tables-dir", default=str(REPO_ROOT / "docs" / "tables"))
    p.add_argument("--scaling-model", default="sidarthe",
                   help="modelul folosit in tabelul de scalare (implicit sidarthe)")
    args = p.parse_args(argv)

    models = args.model or list(ODE_MODELS)
    points = sorted(set(args.points))
    ref = max(points)

    client = Client(args.api_url)
    client.login(args.email, args.password)
    print(f"Autentificat la {args.api_url}")
    print(f"Modele: {models}, puncte: {points}, "
          f"create-repeat={args.create_repeat}, read-repeat={args.read_repeat}\n")

    all_rows: list[dict] = []
    for m in models:
        print(f"  [{m}] ...", flush=True)
        rows = measure_model(client, args.study, args.dataset, m, points,
                             args.create_repeat, args.read_repeat)
        all_rows.extend(rows)
        cr = cell(rows, m, ref, "create", "p50_ms")
        rs = cell(rows, m, ref, "results", "p50_ms")
        kb = cell(rows, m, ref, "results", "bytes") / 1024.0
        print(f"      create p50={cr:.1f} ms | results@{ref} p50={rs:.1f} ms | JSON={kb:.1f} KB")

    out_csv = Path(args.output).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["model", "points", "endpoint",
                                           "p50_ms", "p95_ms", "bytes", "n"])
        w.writeheader()
        for r in all_rows:
            w.writerow({**r, "p50_ms": round(r["p50_ms"], 2),
                        "p95_ms": round(r["p95_ms"], 2), "bytes": int(r["bytes"])})
    print(f"\n-> {out_csv.relative_to(REPO_ROOT)}")

    tables = Path(args.tables_dir)
    write_table_per_model(all_rows, tables / "api_latency.tex", models, ref)
    print(f"-> {(tables / 'api_latency.tex').relative_to(REPO_ROOT)}")
    if args.scaling_model in models:
        write_table_scaling(all_rows, tables / "api_latency_scaling.tex",
                            args.scaling_model, points)
        print(f"-> {(tables / 'api_latency_scaling.tex').relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
