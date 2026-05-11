# Manifeste Kubernetes — Sistem E-Medicine SIDARTH

Directorul conține manifestele declarative pentru rularea întregului sistem pe un cluster Kubernetes. Toate resursele se aplică în namespace-ul `epimodel`.

## Conținut

| Fișier | Resurse | Rol |
|--------|---------|-----|
| `00-namespace.yaml` | `Namespace` | Izolează aplicația într-un namespace dedicat |
| `01-configmap.yaml` | `ConfigMap` | Variabile de configurare non-sensibile (HTTP_ADDR, REDIS_URL, JWT_EXPIRY_HOURS) |
| `02-secret.example.yaml` | `Secret` (template) | Șablon pentru `JWT_SECRET` și `DATABASE_URL` — **nu** aplica direct |
| `10-yugabyte-master.yaml` | `StatefulSet` × 3 + headless `Service` | YugabyteDB master (coordonatorul cluster-ului, port 7100/7000) |
| `11-yugabyte-tserver.yaml` | `StatefulSet` × 3 + headless + ClusterIP `Service` | YugabyteDB tserver (YSQL pe 5433, RPC pe 9100) |
| `20-redis.yaml` | `StatefulSet` × 1 + `Service` | Coadă de mesaje Redis cu persistență AOF |
| `30-migrate-job.yaml` | `Job` | Rulează migrațiile SQL prin `golang-migrate` |
| `40-api.yaml` | `Deployment` × 2 + `Service` | Backend Go (REST API) |
| `50-runner-python.yaml` | `Deployment` × 1 | Runner Python (scipy `solve_ivp`) |
| `51-runner-r.yaml` | `Deployment` × 1 | Runner R (`deSolve::ode`) |
| `52-runner-julia.yaml` | `Deployment` × 1 | Runner Julia (`DifferentialEquations.jl`) |
| `60-frontend.yaml` | `Deployment` × 1 + `Service` | Frontend Vue.js servit prin Nginx |
| `70-ingress.yaml` | `Ingress` | Rutare HTTP externă (`/api` → API, `/` → frontend) |

Prefixele numerice indică ordinea recomandată de aplicare.

## Cerințe preliminare

1. **Cluster Kubernetes** versiune ≥1.28, cu minim 3 noduri (pentru factorul de replicare 3 al YugabyteDB).
2. **`kubectl`** configurat cu contextul corect: `kubectl config current-context`.
3. **Storage Class implicit** disponibil pentru `PersistentVolumeClaim`. Verifică:

   ```bash
   kubectl get storageclass
   ```

   Pe un cluster `kubeadm` minim, instalează un provisioner (ex. `local-path-provisioner` sau `rook-ceph`).
4. **Ingress controller nginx** instalat și expus pe nodurile worker. Documentație: <https://kubernetes.github.io/ingress-nginx/deploy/>.
5. **Registry de imagini** accesibil cluster-ului. Imaginile aplicației (`emedicine/api`, `emedicine/frontend`, `emedicine/runner-python`, `emedicine/runner-r`, `emedicine/runner-julia`) trebuie construite și împinse într-un registry (Docker Hub privat, GHCR, Harbor self-hosted etc.). Pentru un cluster local cu un singur nod, `imagePullPolicy: IfNotPresent` permite folosirea imaginilor build-uite local cu `docker build`.

## Pasul 1 — Build și push al imaginilor

Din rădăcina `code/`:

```bash
# API Go
docker build -t emedicine/api:latest ./api

# Runner-e
docker build -t emedicine/runner-python:latest ./runners/python
docker build -t emedicine/runner-r:latest      ./runners/r
docker build -t emedicine/runner-julia:latest  ./runners/julia

# Frontend
docker build -t emedicine/frontend:latest ./frontend
```

Re-etichetează și împinge într-un registry accesibil cluster-ului:

```bash
REGISTRY=registry.example.com/epimodel
for img in api frontend runner-python runner-r runner-julia; do
  docker tag  emedicine/${img}:latest ${REGISTRY}/${img}:latest
  docker push ${REGISTRY}/${img}:latest
done
```

Apoi înlocuiește `image: emedicine/...` cu `image: ${REGISTRY}/...` în manifestele `40-api.yaml`, `50-...`, `51-...`, `52-...`, `60-frontend.yaml`.

## Pasul 2 — Aplicarea manifestelor

```bash
# 1. Namespace + ConfigMap
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-configmap.yaml

# 2. Secret (generat dintr-o singură comandă, NU din fișier)
kubectl create secret generic epimodel-secrets \
  --namespace=epimodel \
  --from-literal=JWT_SECRET="$(openssl rand -base64 48)" \
  --from-literal=DATABASE_URL="postgres://yugabyte:yugabyte@yb-tserver:5433/yugabyte?sslmode=disable"

# 3. YugabyteDB (master mai întâi, apoi tserver)
kubectl apply -f 10-yugabyte-master.yaml
kubectl apply -f 11-yugabyte-tserver.yaml

# Așteaptă până când toate pod-urile sunt Ready
kubectl rollout status statefulset/yb-master  -n epimodel --timeout=5m
kubectl rollout status statefulset/yb-tserver -n epimodel --timeout=5m

# 4. Redis
kubectl apply -f 20-redis.yaml
kubectl rollout status statefulset/redis -n epimodel --timeout=2m

# 5. Migrațiile SQL — ConfigMap din fișierele de migrare, apoi Job-ul
kubectl create configmap db-migrations \
  --namespace=epimodel \
  --from-file=../db/migrations/
kubectl apply -f 30-migrate-job.yaml
kubectl wait --for=condition=complete job/db-migrate -n epimodel --timeout=3m

# 6. API
kubectl apply -f 40-api.yaml
kubectl rollout status deployment/api -n epimodel --timeout=2m

# 7. Runner-ele
kubectl apply -f 50-runner-python.yaml
kubectl apply -f 51-runner-r.yaml
kubectl apply -f 52-runner-julia.yaml

# 8. Frontend
kubectl apply -f 60-frontend.yaml

# 9. Ingress
kubectl apply -f 70-ingress.yaml
```

Sau, după ce ai creat Secret-ul și ConfigMap-ul cu migrațiile, aplică tot directorul deodată:

```bash
kubectl apply -f .
```

## Pasul 3 — Verificare post-deploy

```bash
# Toate pod-urile
kubectl get pods -n epimodel

# Toate serviciile + ingress
kubectl get svc,ingress -n epimodel

# Health check al API-ului
kubectl exec -n epimodel deploy/api -- wget -qO- http://localhost:8080/api/health

# Verifică job-ul de migrațiile
kubectl logs -n epimodel job/db-migrate
```

Toate pod-urile ar trebui să fie `Running` și `1/1 Ready`, cu excepția `db-migrate` care va fi `Completed`.

## Acces la aplicație

Adaugă în `/etc/hosts` de pe mașina locală:

```
<IP-INGRESS-CONTROLLER>  epimodel.local
```

unde `<IP-INGRESS-CONTROLLER>` este IP-ul extern al serviciului ingress-nginx (`kubectl get svc -n ingress-nginx`).

Apoi accesează:

- Aplicație: <http://epimodel.local/>
- API direct: <http://epimodel.local/api/health>
- YugabyteDB UI (port-forward): `kubectl port-forward -n epimodel svc/yb-masters 7000:7000` → <http://localhost:7000>

## Operațiuni comune

```bash
# Scalează runner-ul Python la 3 replici (paralelism crescut)
kubectl scale -n epimodel deploy/runner-python --replicas=3

# Reîncarcă API-ul după un push de imagine nouă
kubectl rollout restart deploy/api -n epimodel

# Loguri live de la un runner
kubectl logs -f -n epimodel deploy/runner-julia

# Re-rulează migrațiile după ce ai adăugat o nouă migrație
kubectl delete job db-migrate -n epimodel
kubectl create configmap db-migrations -n epimodel \
  --from-file=../db/migrations/ \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f 30-migrate-job.yaml
```

## Cleanup

```bash
# Șterge toate resursele aplicației, păstrând PVC-urile (date YugabyteDB / Redis)
kubectl delete -f .

# Pentru un cleanup complet (inclusiv volumele persistente):
kubectl delete namespace epimodel
```

## Observații pentru un deployment real

- **Parolă YugabyteDB**: parola default `yugabyte:yugabyte` este acceptabilă într-un cluster izolat în rețea, dar pentru un deployment expus extern trebuie rotată. Setează parola cu `ALTER USER yugabyte PASSWORD '...'` și actualizează `DATABASE_URL` în Secret.
- **TLS la Ingress**: secțiunea `tls:` lipsește din `70-ingress.yaml` pentru simplitate. Adaugă-o împreună cu un emitator certificate (`cert-manager` + Let's Encrypt) pentru producție.
- **NetworkPolicy**: nu sunt definite policy-uri de rețea. Pentru zero-trust intra-cluster, adaugă `NetworkPolicy`-uri care să permită explicit doar fluxurile API → DB, API → Redis, Runner → DB, Runner → Redis, Frontend → API.
- **Resource limits**: valorile setate sunt orientative pentru un cluster mic (Dell OptiPlex 7040, 8 GB RAM/nod). Ajustează `requests`/`limits` pe baza monitorizării reale.
- **Backup**: pentru date critice configurează `yb-admin` snapshots periodice sau replicare cross-cluster.
