# Scripturi de date

## `preprocess_owid.py`

Generează 10 CSV-uri SIR (câte unul per țară) din datele brute Our World in Data COVID-19.

### Utilizare

```bash
# instalare dependențe
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# rulare completă (toate 10 țări)
python preprocess_owid.py

# doar o țară (pentru debug)
python preprocess_owid.py --country ROU

# forțează re-download (raw CSV se cache-uiește în code/data/raw/)
python preprocess_owid.py --force-download
```

Sau prin Makefile (din `code/`):

```bash
make data       # rulează preprocesarea
```

### Input

- **Sursa:** https://covid.ourworldindata.org/data/owid-covid-data.csv
- **Cache:** `code/data/raw/owid-covid-data.csv` (~80–100 MB, descărcat o singură dată)

### Output

10 CSV-uri în `code/data/processed/`, fiecare cu schema așteptată de `POST /api/datasets`:

| Coloană | Tip | Sursă |
|---------|-----|-------|
| `date`        | YYYY-MM-DD | OWID `date` |
| `region`      | ISO 3166-1 alpha-3 | OWID `iso_code` |
| `infected`    | int   | $\sum_{\tau=t-13}^{t}$ `new_cases` (fereastră 14 zile) |
| `population`  | int   | OWID `population` (primul non-null) |
| `recovered`   | int   | `total_cases - infected` (removed = recuperați + decedați) |
| `susceptible` | int   | $N$ - `infected` - `recovered` |

### Cele 10 țări

| ISO3 | Slug fișier              |
|------|--------------------------|
| ROU  | `romania.csv`            |
| ITA  | `italy.csv`              |
| KOR  | `south_korea.csv`        |
| DEU  | `germany.csv`            |
| GBR  | `united_kingdom.csv`     |
| USA  | `united_states.csv`      |
| BRA  | `brazil.csv`             |
| SWE  | `sweden.csv`             |
| JPN  | `japan.csv`              |
| IND  | `india.csv`              |

### Validări aplicate

- compartimente >= 0 pentru fiecare $t$
- $I(t) + R(t) \leq N$
- date ordonate cronologic, fără goluri > 14 zile (zilele lipsă sunt completate prin forward-fill al cumulativilor și zero-fill pentru `new_cases`)

### Fereastra temporală

**22 ianuarie 2020 → 31 decembrie 2023** (~1440 zile per țară).

Acoperă întregul ciclu pandemic (toate valurile majore, lansarea vaccinurilor, valurile Omicron) până când raportarea oficială devine sporadică în 2024.
