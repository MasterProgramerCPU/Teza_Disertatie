"""Generator de date sintetice per județ pentru Romania.

Pornește de la seria națională OWID (data/processed/romania.csv) și distribuie
fiecare metrică pe județe, ponderată după populația din 2011. Pentru a face
hărțile interesante (nu doar scala-invariantă), aplică o perturbare aleatoare
specifică fiecărui județ (rng deterministic seed pe codul mnemonic), astfel
încât județele să aibă rate diferite per 100k locuitori — exact ce avem nevoie
ca demo pentru pagina hartă.

Output: data/processed/ro_judete/RO-XX.csv pentru fiecare județ, cu coloana
region="RO-XX".
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
OUT_DIR = PROCESSED / "ro_judete"
GEOJSON = ROOT.parent / "code" / "frontend" / "public" / "geo" / "romania-counties.geojson"

NATIONAL_CSV = PROCESSED / "romania.csv"

OPTIONAL_INT_COLS = [
    "infected", "recovered", "susceptible", "population",
    "deaths", "new_cases", "new_deaths",
    "hospitalized", "icu", "vaccinated", "tested",
]
OPTIONAL_FLOAT_COLS = ["stringency_index", "reproduction_rate"]


def load_counties() -> list[dict]:
    with GEOJSON.open() as fh:
        fc = json.load(fh)
    counties = []
    for f in fc["features"]:
        p = f["properties"]
        counties.append({
            "code": p["COUNTY_CODE"],
            "name": p["NAME"],
            "pop": int(p.get("POP_2011") or 0),
        })
    return counties


def seed_factor(code: str) -> float:
    """Factor multiplicativ stabil per județ în [0.55, 1.55]. Deterministic
    pe baza codului mnemonic, astfel încât rezultatele să fie reproductibile."""
    h = int(hashlib.sha256(code.encode()).hexdigest()[:8], 16)
    return 0.55 + (h % 1000) / 1000.0  # 0.55..1.55


def parse_int(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def parse_float(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> None:
    counties = load_counties()
    total_pop = sum(c["pop"] for c in counties)
    print(f"Județe: {len(counties)}, populație totală (2011): {total_pop:,}")

    # Read national CSV in memory
    with NATIONAL_CSV.open() as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    print(f"Rânduri naționale: {len(rows)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for c in counties:
        share = c["pop"] / total_pop
        factor = seed_factor(c["code"])
        out_path = OUT_DIR / f"{c['code']}.csv"
        with out_path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([
                "date", "region", "infected", "population", "recovered",
                "susceptible", "deaths", "new_cases", "new_deaths",
                "hospitalized", "icu", "vaccinated", "tested",
                "stringency_index", "reproduction_rate",
            ])
            for r in rows:
                pop_county = c["pop"]
                # Scalăm metricile epi după populație × factor specific
                def s_int(col: str) -> str:
                    v = parse_int(r.get(col, "") or "")
                    if v is None:
                        return ""
                    if col == "population":
                        return str(pop_county)
                    scaled = round(v * share * factor)
                    return str(max(scaled, 0))

                def s_float(col: str) -> str:
                    v = parse_float(r.get(col, "") or "")
                    if v is None:
                        return ""
                    # stringency / R_t sunt indicatori — nu îi scalăm
                    return f"{v:.4f}".rstrip("0").rstrip(".") if v else "0"

                # susceptible recomputat din pop_county - infected - recovered
                infected = parse_int(r.get("infected", "") or "") or 0
                recovered = parse_int(r.get("recovered", "") or "") or 0
                scaled_infected = round(infected * share * factor)
                scaled_recovered = round(recovered * share * factor)
                susceptible = max(pop_county - scaled_infected - scaled_recovered, 0)

                w.writerow([
                    r["date"],
                    c["code"],
                    scaled_infected,
                    pop_county,
                    scaled_recovered,
                    susceptible,
                    s_int("deaths"),
                    s_int("new_cases"),
                    s_int("new_deaths"),
                    s_int("hospitalized"),
                    s_int("icu"),
                    s_int("vaccinated"),
                    s_int("tested"),
                    s_float("stringency_index"),
                    s_float("reproduction_rate"),
                ])
        print(f"  → {c['code']} ({c['name']}) pop={c['pop']:,} factor={factor:.2f}")

    print(f"\nGata: {len(counties)} CSV-uri scrise în {OUT_DIR}")


if __name__ == "__main__":
    main()
