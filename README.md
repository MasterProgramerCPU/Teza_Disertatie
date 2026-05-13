# Sistem E-Medicine SIR Workbench

Lucrare de disertație + implementare funcțională pentru un sistem e-medicine
care permite analiza datelor epidemiologice prin modele compartimentale
**SIDARTHE**, **SIR**, **SIS**, **SEIR** și **SIRS**, plus predicție
univariată **LSTM**, cu execuție paralelă în trei limbaje de programare
(R, Julia, Python), runner ML dedicat și deploy nativ pe Kubernetes.

> **Autor:** Tudor-Bogdan Geană (master IISC, UNSTPB / Facultatea ETTI)
> **Coordonator:** Prof. Dr. Ing. Radu Rădescu
> **Anul:** 2026

---

## Structura repository-ului

```
.
├── docs/                  # Lucrarea de disertație (LaTeX)
│   ├── main.tex
│   ├── chapters/          # Cap. 0–8 (Rezumat, Introducere, ... , Concluzii)
│   ├── appendices/        # Anexe A–G (cod R/Julia/Python/LSTM, schema BD, K8s, REST)
│   └── bibliography.bib
│
├── code/                  # Implementare end-to-end
│   ├── api/               # Backend Go (REST API, JWT, RBAC pe studii)
│   ├── runners/           # Python / R / Julia / LSTM — consumatori coadă Redis
│   ├── frontend/          # SPA user (Vue 3 + Pinia + Vite)
│   ├── frontend-admin/    # SPA super-admin separat (build distinct)
│   ├── db/migrations/     # migrații SQL idempotente
│   ├── k8s/               # Manifeste Kubernetes (1 fișier per componentă)
│   ├── scripts/           # Preprocesare OWID COVID-19 → CSV per țară
│   ├── data/              # Cache OWID + 38 dataseturi procesate
│   ├── docker-compose.yml # Mediu local complet
│   └── Makefile
│
└── README.md              # (acest fișier)
```

---

## Arhitectura (vedere de ansamblu)

```
                            ┌─────────────────┐
                            │  Browser user   │
                            └─────────────────┘
                                     │
             sir-workbench.ro / admin.sir-workbench.ro
                                     │
                              ┌──────▼──────┐
                              │  ingress-   │
                              │  nginx      │
                              └─┬─┬─────┬───┘
                                │ │     │
            ┌───────────────────┘ │     └────────────────────┐
            ▼                     ▼                          ▼
   ┌────────────────┐    ┌────────────────┐         ┌────────────────┐
   │ frontend       │    │ frontend-admin │         │  API Go (×2)   │
   │ Vue 3 (Nginx)  │    │ Vue 3 (Nginx)  │         │  chi + JWT +   │
   │                │    │                │         │  RBAC studii   │
   └────────────────┘    └────────────────┘         └───┬────────┬───┘
                                                       │        │
                                       LPUSH/BRPOP     │        │ YSQL 5433
                                                       ▼        ▼
                                            ┌──────────────┐  ┌─────────────────┐
                                            │  Redis       │  │  YugabyteDB     │
                                            │  (cozi job)  │  │  RF=3           │
                                            └──────┬───────┘  │  3 master + 3   │
                                                   │ BRPOP    │  tserver        │
                               ┌───────────┼──────────┬──────────┐  └─────────────────┘
                               ▼           ▼          ▼          ▼          ▲
                          ┌────────┐  ┌────────┐ ┌────────┐ ┌────────┐      │
                          │runner-r│  │runner- │ │runner- │ │runner- │ INSERT
                          │        │  │ python │ │ julia  │ │ lstm   │      │
                          └────────┘  └────────┘ └────────┘ └────────┘──────┘
```

**Patru straturi funcționale:**

1. **Prezentare** — două SPA-uri Vue 3 separate (user + super-admin) servite
   prin Nginx, cu rute Vue Router în mod history.
2. **API** — server Go (chi router, pgx, JWT HS256), două replici cu
   anti-affinity. Endpoint-uri organizate pe trei axe:
   - public (`/api/auth/*`, `/api/health`)
   - scope studiu (`/api/studies/{id}/...`) cu middleware RBAC
   - super-admin (`/api/admin/*`) cu middleware `RequireSuperAdmin`
3. **Calcul** — runner-e compartimentale în R, Julia și Python, plus un
   runner LSTM separat pentru predicții; fiecare consumă o coadă Redis dedicată
   (`epimodel:jobs:{r,julia,python,lstm}`).
4. **Stocare** — YugabyteDB cu factor de replicare 3 (8 tabele aplicative,
   12 migrații SQL, 79 dataseturi, ~113 000 înregistrări epidemiologice OWID
   2020-2023, 4 roluri RBAC).

---

## Model RBAC: studii + roluri

Toate datele sunt **scope pe studiu** (un studiu = un context epidemiologic,
de obicei o boală + o cohortă). Un utilizator poate fi membru în multiple
studii, cu rol diferit în fiecare.

| Rol | Vede | Upload dataset | Lansează simulare | Gestionează membri |
|---|:---:|:---:|:---:|:---:|
| **admin**       | ✓ | ✓ | ✓ | ✓ |
| **researcher**  | ✓ | — | ✓ | — |
| **contributor** | ✓ | ✓ | — | — |
| **viewer**      | ✓ | — | — | — |

Pe deasupra există flag-ul **super-admin** la nivel de user: acordă acces la
toate studiile (fără să fie membru) + consola dedicată `admin.sir-workbench.ro` cu
statistici globale și gestionarea utilizatorilor (promovare / revocare).

---

## Cele două front-end-uri

| Aplicație | Host (prin Ingress) | Public țintă | Caracteristici |
|---|---|---|---|
| **frontend** | `http://sir-workbench.ro` | Cercetători, editori | Selector de studiu, dashboard, upload CSV, lansare simulare, grafice, benchmarks |
| **frontend-admin** | `http://admin.sir-workbench.ro` | Super-admin | Dashboard global, listă useri (cu promote/revoke), listă studii cross-tenant |

Cele două SPA-uri **partajează API-ul** și mecanismul JWT, dar:
- au build-uri Docker separate;
- folosesc chei distincte în `localStorage` (`emedicine.token` vs
  `emedicine-admin.token`), deci login-urile sunt independente;
- consola admin **refuză** explicit credentialele utilizatorilor obișnuiți
  (`is_super_admin == false` → eroare la login).

---

## Tehnologii

| Componentă | Stack |
|---|---|
| **Backend API** | Go 1.25, chi router, pgx/v5, golang-jwt, bcrypt |
| **Runner-e** | Python 3.12 + scipy / R 4.4 + deSolve / Julia 1.11 + DifferentialEquations.jl |
| **Frontend** | Vue 3 + Vite + TypeScript + Pinia + Vue Router + Chart.js |
| **Bază de date** | YugabyteDB 2024.1 (PostgreSQL-compatible), RF=3 |
| **Cozi mesaje** | Redis 7 |
| **Container runtime** | containerd 1.7 |
| **Orchestrator** | Kubernetes v1.31 (3 control-plane + 3 worker, CNI Cilium) |
| **Ingress** | ingress-nginx (Helm chart oficial) |
| **Registry imagini** | GitHub Container Registry (`ghcr.io/masterprogramercpu/emedicine-*`) |
| **Build LaTeX** | `latexmk` cu pdflatex + BibTeX |

---

## Pornire locală cu Docker Compose

```bash
cd code/
cp .env.example .env
# editează JWT_SECRET la o valoare reală
make up
make health
```

`make up` pornește mediul local complet:

| Serviciu | Rol | Porturi locale |
|---|---|---|
| **YugabyteDB** | YSQL + stocare distribuită în variantă single-node locală | `5433`, `7000` |
| **Redis** | cozi pentru joburile de simulare | `6379` |
| **migrate** | aplică migrațiile SQL idempotente | — |
| **API Go** | REST API + JWT + RBAC pe studii | `8080` |
| **runner-python / runner-r / runner-julia** | consumă joburi compartimentale din `epimodel:jobs:{python,r,julia}` | — |
| **runner-lstm** | consumă joburi LSTM din `epimodel:jobs:lstm` | — |

Primul build poate dura 10-15 minute deoarece runner-ele instalează pachete
native: R compilează `deSolve` / `RPostgres`, iar Julia precompilează
`DifferentialEquations.jl`. Build-urile ulterioare folosesc cache-ul Docker.

---

## API REST

Endpointurile sunt organizate în jurul studiilor, pentru ca datele și
simulările să rămână izolate pe context epidemiologic:

| Zonă | Endpointuri principale | Auth |
|---|---|---|
| Public | `GET /api/health`, `POST /api/auth/register`, `POST /api/auth/login` | nu |
| Utilizator | `GET /api/me` | JWT |
| Studii | `GET/POST /api/studies`, `GET/PUT/DELETE /api/studies/{id}` | JWT |
| Membri studiu | `/api/studies/{id}/members` | rol `admin` pe studiu |
| Dataseturi | `/api/studies/{id}/datasets`, `/api/studies/{id}/datasets/{datasetId}` | RBAC pe studiu |
| Simulări | `/api/studies/{id}/simulations`, `/api/studies/{id}/simulations/{runId}/results`, `/export` | RBAC pe studiu |
| Benchmarks | `/api/studies/{id}/benchmarks` | RBAC pe studiu |
| Super-admin | `/api/admin/*` | `is_super_admin=true` |

Modele acceptate în `model_type`:

| Familie | Valori | Compartimente |
|---|---|---|
| Clinic COVID-19 | `sidarthe` | 8 compartimente |
| SIR | `sir`, `sis`, `seir`, `sirs` | 2-4 compartimente |
| Predicție ML | `lstm` | `observed`, `fitted`, `predicted` |

Exemplu minim de flow prin API:

```bash
# 1. Înregistrare
curl -X POST localhost:8080/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"tudor@example.com","password":"parolasecreta"}'

# 2. Login
TOKEN=$(curl -s -X POST localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"tudor@example.com","password":"parolasecreta"}' \
  | jq -r .data.token)

# 3. Creare studiu
STUDY_ID=$(curl -s -X POST localhost:8080/api/studies \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"COVID-19 România","disease_code":"COVID-19","description":"Studiu local"}' \
  | jq -r .data.id)

# 4. Upload dataset CSV
DATASET_ID=$(curl -s -X POST "localhost:8080/api/studies/$STUDY_ID/datasets" \
  -H "Authorization: Bearer $TOKEN" \
  -F name="COVID-19 RO" \
  -F disease_code="COVID-19" \
  -F file=@/path/to/data.csv \
  | jq -r .data.id)

# 5. Inițiere simulare SIDARTHE pe runner-ul Python
curl -X POST "localhost:8080/api/studies/$STUDY_ID/simulations" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{
    \"dataset_id\":\"$DATASET_ID\",
    \"model_type\":\"sidarthe\",
    \"language\":\"python\",
    \"parameters\":{
      \"alpha\":0.57,
      \"beta\":0.011,
      \"gamma\":0.456,
      \"delta\":0.011,
      \"epsilon\":0.171,
      \"zeta\":0.125,
      \"lambda\":0.034,
      \"eta\":0.125,
      \"rho\":0.034,
      \"theta\":0.37,
      \"mu\":0.017,
      \"kappa\":0.017,
      \"nu\":0.027,
      \"xi\":0.017,
      \"sigma\":0.017,
      \"tau\":0.010
    },
    \"t_max\":160
  }"
```

CSV-ul acceptat are coloane obligatorii `date`, `region`, `infected`,
`population`; coloanele `recovered` și `susceptible` sunt opționale.
Validarea verifică ordinea cronologică și consistența populației.

---

## Runner-ele

Fiecare runner consumă joburi prin `BRPOP`, marchează rularea ca `running`,
rezolvă sistemul selectat, inserează traiectoriile compartimentale în
`simulation_results`, scrie metricile în `benchmarks`, apoi marchează jobul
`completed`.

| Runner | Solver | Pași timp | Client Redis | Driver DB |
|---|---|---|---|---|
| Python | `scipy.integrate.solve_ivp` (RK45 adaptiv) | `t_eval = 0..t_max` | `redis-py` | `psycopg[binary]` |
| R | `deSolve::ode` (`rk4`, h=1) | `times = 0..t_max` | `redux` | `RPostgres` |
| Julia | `DifferentialEquations.solve` (`Tsit5`) | `saveat = 0..t_max` | `Redis.jl` | `LibPQ.jl` |

Metricile colectate sunt `wall_time_ms`, `cpu_time_ms` și `peak_memory_mb`,
calculate cu primitivele standard ale fiecărui limbaj și persistate în tabela
`benchmarks`.

---

## Deploy Kubernetes

Manifestele din `code/k8s/` rulează sistemul complet în namespace-ul
`epimodel`. Configurația a fost testată pe Kubernetes v1.31, cu 3 noduri
control-plane, 3 noduri worker, Cilium, ingress-nginx și YugabyteDB RF=3
instalat prin Helm. Funcționează pe orice cluster Kubernetes >= v1.28 cu
StorageClass implicit și ingress-nginx.

Fișierele principale:

| Fișier | Rol |
|---|---|
| `00-namespace.yaml`, `01-configmap.yaml`, `02-secret.example.yaml` | namespace, configurare și șablon de secrete |
| `10-yugabyte-values.yaml`, `12-yugabyte-tserver-service.yaml` | YugabyteDB RF=3 și service YSQL |
| `20-redis.yaml`, `30-migrate-job.yaml` | Redis și jobul de migrații SQL |
| `40-api.yaml` | API Go cu 2 replici |
| `50-runner-python.yaml`, `51-runner-r.yaml`, `52-runner-julia.yaml`, `53-runner-lstm.yaml` | runner-ele de simulare și predicție |
| `60-frontend.yaml`, `61-frontend-admin.yaml`, `70-ingress.yaml` | cele două SPA-uri și rutarea HTTP |

Aplicare pe cluster:

```bash
cd code/k8s

kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-configmap.yaml

kubectl create secret generic epimodel-secrets \
  --namespace=epimodel \
  --from-literal=JWT_SECRET="$(openssl rand -base64 48)" \
  --from-literal=DATABASE_URL="postgres://yugabyte:yugabyte@yb-tserver-service:5433/yugabyte?sslmode=disable"

helm repo add yugabytedb https://charts.yugabyte.com
helm repo update
helm upgrade --install yugabyte yugabytedb/yugabyte \
  --namespace epimodel \
  -f 10-yugabyte-values.yaml \
  --wait --timeout 10m

kubectl apply -f 12-yugabyte-tserver-service.yaml
kubectl apply -f 20-redis.yaml

kubectl create configmap db-migrations \
  --namespace=epimodel \
  --from-file=../db/migrations/
kubectl apply -f 30-migrate-job.yaml
kubectl wait --for=condition=complete job/db-migrate -n epimodel --timeout=3m

kubectl apply -f 40-api.yaml
kubectl apply -f 50-runner-python.yaml
kubectl apply -f 51-runner-r.yaml
kubectl apply -f 52-runner-julia.yaml
kubectl apply -f 53-runner-lstm.yaml
kubectl apply -f 60-frontend.yaml
kubectl apply -f 61-frontend-admin.yaml
kubectl apply -f 70-ingress.yaml
```

Verificare:

```bash
kubectl get pods -n epimodel
kubectl get svc,ingress -n epimodel
kubectl exec -n epimodel deploy/api -- wget -qO- http://localhost:8080/api/health
```

Operațiuni utile:

```bash
# crește paralelismul Python
kubectl scale -n epimodel deploy/runner-python --replicas=3

# crește paralelismul pentru predicții LSTM
kubectl scale -n epimodel deploy/runner-lstm --replicas=2

# restart după push de imagine nouă
kubectl rollout restart deploy/api -n epimodel
kubectl rollout restart deploy/frontend -n epimodel
kubectl rollout restart deploy/frontend-admin -n epimodel

# loguri live runner
kubectl logs -f -n epimodel deploy/runner-julia
```

---

## Demo rapid (rulând în K8s cu port-forward)

```bash
# Pornește port-forward către ingress (necesită sudo pentru port 80)
sudo kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 80:80

# Adaugă în /etc/hosts (o singură dată)
echo "127.0.0.1 sir-workbench.ro" | sudo tee -a /etc/hosts
echo "127.0.0.1 admin.sir-workbench.ro" | sudo tee -a /etc/hosts
```

Apoi în browser:
- **http://sir-workbench.ro** — login + dashboard normal
- **http://admin.sir-workbench.ro** — consolă super-admin

### Conturi demo (toate cu parola `parola1234`)

| Email | Acces |
|---|---|
| `tudor@test.ro` | Super-admin global + admin în „COVID-19 — Europa" |
| `admin@demo.ro` | admin în „COVID-19 — Europa" |
| `cercetator@demo.ro` | researcher în „COVID-19 — Europa" |
| `contributor@demo.ro` | contributor în „COVID-19 — Europa" |
| `viewer@demo.ro` | viewer în „COVID-19 — Europa" |

---

## Date

**Sursa:** Our World in Data — COVID-19. Sunt incluse **38 țări europene**
(UE 27 + UK + EFTA + Balcani + Moldova + Ucraina), perioada 2020-01-22 →
2023-12-31, granularitate zilnică. Derivare compartimentală în
`code/scripts/preprocess_owid.py`.

**În BD:** 40 studii (38 per țară + 1 reunit „Europa" + 1 pilot inițial),
79 dataseturi (țările europene apar atât per-studiu, cât și în studiul Europa,
fără cross-study referencing), ~113 760 înregistrări epidemiologice zilnice.

---

## Preprocesare date OWID

Scriptul `code/scripts/preprocess_owid.py` descarcă sau refolosește cache-ul
OWID, filtrează intervalul 2020-01-22 → 2023-12-31, completează calendarul
zilnic și derivează compartimentele observabile:

| Coloană | Sursă / calcul |
|---|---|
| `date` | OWID `date` |
| `region` | ISO 3166-1 alpha-3 |
| `infected` | suma `new_cases` pe ultimele 14 zile |
| `population` | OWID `population` |
| `recovered` | `total_cases - infected` |
| `susceptible` | `population - infected - recovered` |

Rulare:

```bash
cd code/
make data

# sau direct, pentru debug
cd scripts/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python preprocess_owid.py --country ROU
python preprocess_owid.py --force-download
```

Output-ul este scris în `code/data/processed/` și are schema acceptată de
`POST /api/studies/{studyId}/datasets`.

---

## Lucrarea de disertație

Documentul LaTeX este în `docs/`, iar PDF-ul generat este `docs/main.pdf`.
Build:

```bash
cd docs
latexmk -pdf main.tex
```

---

## Licență

Cod open-source pentru uz academic, fără licență comercială specifică.
Datele OWID sunt sub licență Creative Commons BY 4.0 (vezi
https://github.com/owid/covid-19-data).
