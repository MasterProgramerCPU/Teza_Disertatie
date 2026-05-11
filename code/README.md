# Sistem E-Medicine SIR — Cod sursă

Acest director conține implementarea sistemului descris în lucrare.

## Structura

```
code/
├── api/                    # Backend Go (REST API)
│   ├── cmd/server/         # Entry point
│   ├── internal/
│   │   ├── api/
│   │   │   ├── handlers/   # HTTP handlers (auth, datasets, simulations, benchmarks, health)
│   │   │   ├── middleware/ # JWT auth middleware
│   │   │   └── router/     # chi router config
│   │   ├── config/         # Config din env vars
│   │   ├── db/repository/  # Repository pattern peste pgx
│   │   ├── runner/         # Redis dispatcher pentru job-uri
│   │   └── models/         # Struct-uri de domeniu
│   ├── pkg/sirmath/        # (rezervat) implementare SIR de referință în Go
│   ├── go.mod
│   └── Dockerfile
├── runners/                # Cele 3 runner-e SIR (BRPOP consumer)
│   ├── python/             # scipy.integrate.solve_ivp (RK45)
│   ├── r/                  # deSolve::ode (rk4, h=1)
│   └── julia/              # DifferentialEquations.jl (Tsit5)
├── db/migrations/          # Migrații SQL (golang-migrate)
├── k8s/                    # (rezervat) manifeste Kubernetes
├── scripts/                # (rezervat) script preprocesare OWID
├── docker-compose.yml      # YugabyteDB + Redis + API + 3 runner-e
└── Makefile
```

## Pornire rapidă

```bash
cd code/
cp .env.example .env
# editează JWT_SECRET la ceva real
make up
make health
```

`make up` pornește:
1. **YugabyteDB** (single-node, port 5433 pentru YSQL, 7000 pentru UI)
2. **Redis** (port 6379)
3. **migrate** rulează migrațiile pe YugabyteDB
4. **API** Go pornește pe port 8080
5. **runner-python, runner-r, runner-julia** — consumă fiecare coada sa Redis (`sir:jobs:{python,r,julia}`)

> **Notă:** Primul `make up` durează 10–15 minute pentru build-ul runner-elor (R compilează `deSolve`/`RPostgres` din sursă, Julia precompilează `DifferentialEquations.jl`). Build-urile sunt cache-uite ulterior.

## Endpointuri REST

| Metodă | Cale | Auth |
|--------|------|------|
| GET    | `/api/health`              | nu  |
| POST   | `/api/auth/register`       | nu  |
| POST   | `/api/auth/login`          | nu  |
| GET    | `/api/datasets`            | da  |
| POST   | `/api/datasets`            | da  |
| GET    | `/api/datasets/{id}`       | da  |
| DELETE | `/api/datasets/{id}`       | da  |
| GET    | `/api/simulations`         | da  |
| POST   | `/api/simulations`         | da  |
| GET    | `/api/simulations/{id}`    | da  |
| GET    | `/api/simulations/{id}/results` | da |
| GET    | `/api/simulations/{id}/export`  | da |
| GET    | `/api/benchmarks`          | da  |

## Exemplu de utilizare

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

# 3. Upload dataset CSV (header: date,region,infected,population,recovered,susceptible)
curl -X POST localhost:8080/api/datasets \
  -H "Authorization: Bearer $TOKEN" \
  -F name="COVID-19 RO" -F disease_code="COVID-19" \
  -F file=@/path/to/data.csv

# 4. Inițiere simulare
curl -X POST localhost:8080/api/simulations \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset_id":"<id>",
    "language":"python",
    "beta":0.3,
    "gamma":0.0714,
    "t_max":160
  }'
```

## Note tehnice

- **Schema BD:** 6 tabele (`users`, `datasets`, `epidemiological_records`, `simulation_runs`, `simulation_results`, `benchmarks`) — vezi `db/migrations/`
- **Comunicarea cu runner-ele:** API publică job-uri în lista Redis `sir:jobs:<language>` prin `LPUSH`; runner-ele consumă cu `BRPOP` (modelul descris în capitolul 4 al lucrării)
- **JWT:** HS256, expirare 24h, parole hash-uite cu bcrypt cost 12
- **Validare CSV:** coloane obligatorii `date`, `region`, `infected`, `population`; opționale `recovered`, `susceptible`; verifică $I+R \leq N$ și ordinea cronologică

## Runner-ele

Fiecare runner expune același comportament: BRPOP din coada sa, marchează rularea ca `running`, rezolvă SIR, face bulk insert al rezultatelor, scrie metricile în `benchmarks`, marchează `completed`.

| Runner | Solver | Pași timp | Client Redis | Driver DB |
|--------|--------|-----------|--------------|-----------|
| Python | `scipy.integrate.solve_ivp` (RK45 adaptiv) | `t_eval = 0..t_max` | `redis-py` | `psycopg[binary]` |
| R      | `deSolve::ode` (method=`rk4`, h=1) | `times = 0..t_max` | `redux` | `RPostgres` |
| Julia  | `DifferentialEquations.solve` (`Tsit5`) | `saveat = 0..t_max` | `Redis.jl` | `LibPQ.jl` |

Metricile colectate (toate scrise în tabela `benchmarks`):
- `wall_time_ms` — `time.perf_counter()` / `proc.time()["elapsed"]` / `time_ns()`
- `cpu_time_ms`  — `time.process_time()` / `proc.time()["user.self"+"sys.self"]` / elapsed (Julia)
- `peak_memory_mb` — `getrusage().ru_maxrss` / `/proc/self/status:VmHWM` / `Sys.maxrss()`

## Componente care urmează

- [ ] Script preprocesare OWID → CSV-uri SIR (România/Italia/Coreea de Sud)
- [ ] Frontend Vue.js
- [ ] Manifeste Kubernetes (pentru deploy pe clusterul fizic)
