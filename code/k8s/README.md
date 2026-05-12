# Manifeste Kubernetes — Sistem E-Medicine SIDARTH

Directorul conține manifestele declarative pentru rularea întregului sistem pe un cluster Kubernetes. Toate resursele se aplică în namespace-ul `epimodel`.

Manifestele sunt scrise și testate pentru clusterul `kube-4kdhb` (OpenStack, 3 control-plane + 3 worker cu 2 vCPU / 4 GiB fiecare, K8s v1.31, Cilium CNI, CSI Cinder cu `block-ceph` ca StorageClass default). Funcționează și pe orice alt cluster ≥ v1.28 cu un StorageClass implicit + ingress-nginx instalat.

## Conținut

| Fișier | Resurse | Rol |
|--------|---------|-----|
| `00-namespace.yaml` | `Namespace` | Izolează aplicația într-un namespace dedicat |
| `01-configmap.yaml` | `ConfigMap` | Variabile non-sensibile (HTTP_ADDR, REDIS_URL, JWT_EXPIRY_HOURS) |
| `02-secret.example.yaml` | `Secret` (template) | Șablon pentru `JWT_SECRET` și `DATABASE_URL` — **nu** aplica direct |
| `10-yugabyte-values.yaml` | Helm values | Valori pentru chart-ul oficial `yugabytedb/yugabyte` (RF=3, profil PoC) |
| `20-redis.yaml` | `StatefulSet` + `Service` | Coadă de mesaje Redis cu persistență AOF |
| `30-migrate-job.yaml` | `Job` | Rulează migrațiile SQL prin `golang-migrate` |
| `40-api.yaml` | `Deployment` × 2 + `Service` | Backend Go (REST API) |
| `50-runner-python.yaml` | `Deployment` × 1 | Runner Python (scipy `solve_ivp`) |
| `51-runner-r.yaml` | `Deployment` × 1 | Runner R (`deSolve::ode`) |
| `52-runner-julia.yaml` | `Deployment` × 1 | Runner Julia (`DifferentialEquations.jl`) |
| `60-frontend.yaml` | `Deployment` + `Service` | Frontend Vue.js servit prin Nginx |
| `70-ingress.yaml` | `Ingress` | Rutare HTTP (`/api` → API, `/` → frontend) |

Prefixele numerice indică ordinea recomandată de aplicare.

## Cerințe preliminare

1. **Cluster Kubernetes** versiune ≥ 1.28, cu minim 3 noduri (pentru RF=3 YugabyteDB).
2. **`kubectl`** configurat: `kubectl config current-context`.
3. **Storage Class implicit:**
   ```bash
   kubectl get storageclass
   ```
   Pe `kube-4kdhb` default este `block-ceph` (Cinder/Ceph). Folosit explicit în `10-yugabyte-values.yaml`.
4. **Ingress controller nginx** instalat. Verifică:
   ```bash
   kubectl get ingressclass
   ```
   Dacă lipsește, instalează cu:
   ```bash
   helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
   helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
     --namespace ingress-nginx --create-namespace \
     --set controller.service.type=ClusterIP \
     --set controller.ingressClassResource.default=true
   ```
   (Pe `kube-4kdhb` folosim `ClusterIP` pentru că Octavia LB nu e disponibil; accesul se face prin `kubectl port-forward`. Pe un cluster cu provider LB funcțional, schimbă în `LoadBalancer`.)
5. **metrics-server** (opțional, dar necesar pentru `kubectl top` și HPA):
   ```bash
   helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
   helm upgrade --install metrics-server metrics-server/metrics-server \
     --namespace kube-system \
     --set args='{--kubelet-insecure-tls}'
   ```
6. **Registry de imagini** accesibil clusterului. Imaginile aplicației (`emedicine/api`, `emedicine/frontend`, `emedicine/runner-python`, `emedicine/runner-r`, `emedicine/runner-julia`) trebuie construite și împinse într-un registry public (GHCR / Docker Hub / Harbor).

## Pasul 1 — Build și push al imaginilor

Din rădăcina `code/`:

```bash
REGISTRY=ghcr.io/<user-github>/sidarth   # sau docker.io/<user>/sidarth

docker build -t ${REGISTRY}/api:latest             ./api
docker build -t ${REGISTRY}/runner-python:latest   ./runners/python
docker build -t ${REGISTRY}/runner-r:latest       ./runners/r
docker build -t ${REGISTRY}/runner-julia:latest    ./runners/julia
docker build -t ${REGISTRY}/frontend:latest        ./frontend

docker push ${REGISTRY}/api:latest
docker push ${REGISTRY}/runner-python:latest
docker push ${REGISTRY}/runner-r:latest
docker push ${REGISTRY}/runner-julia:latest
docker push ${REGISTRY}/frontend:latest
```

Apoi în `40-api.yaml`, `50/51/52-runner-*.yaml`, `60-frontend.yaml` înlocuiește `emedicine/<img>:latest` cu `${REGISTRY}/<img>:latest`.

## Pasul 2 — Aplicarea manifestelor

```bash
# 0. Namespace + ConfigMap
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-configmap.yaml

# 1. Secret (NU din fisier — generat imperativ)
kubectl create secret generic epimodel-secrets \
  --namespace=epimodel \
  --from-literal=JWT_SECRET="$(openssl rand -base64 48)" \
  --from-literal=DATABASE_URL="postgres://yugabyte:yugabyte@yb-tserver-service:5433/yugabyte?sslmode=disable"

# 2. YugabyteDB via Helm
helm repo add yugabytedb https://charts.yugabyte.com
helm repo update
helm upgrade --install yugabyte yugabytedb/yugabyte \
  --namespace epimodel \
  -f 10-yugabyte-values.yaml \
  --wait --timeout 10m

# 3. Redis
kubectl apply -f 20-redis.yaml
kubectl rollout status statefulset/redis -n epimodel --timeout=2m

# 4. Migrații SQL — ConfigMap din fișierele de migrare, apoi Job
kubectl create configmap db-migrations \
  --namespace=epimodel \
  --from-file=../db/migrations/
kubectl apply -f 30-migrate-job.yaml
kubectl wait --for=condition=complete job/db-migrate -n epimodel --timeout=3m

# 5. API + runnere + frontend
kubectl apply -f 40-api.yaml
kubectl apply -f 50-runner-python.yaml
kubectl apply -f 51-runner-r.yaml
kubectl apply -f 52-runner-julia.yaml
kubectl apply -f 60-frontend.yaml

# 6. Ingress
kubectl apply -f 70-ingress.yaml
```

## Pasul 3 — Verificare post-deploy

```bash
kubectl get pods -n epimodel
kubectl get svc,ingress -n epimodel
kubectl exec -n epimodel deploy/api -- wget -qO- http://localhost:8080/api/health
kubectl logs -n epimodel job/db-migrate
```

Toate pod-urile ar trebui să fie `Running` și `Ready`, cu excepția `db-migrate` care va fi `Completed`.

## Acces la aplicație (pe `kube-4kdhb`)

Pentru că Octavia LB nu funcționează acum, expunerea publică nu e posibilă. Accesul se face prin `kubectl port-forward` la ingress-nginx:

```bash
# Terminal 1: tunel local către ingress-nginx
kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80

# /etc/hosts (o singură dată):
echo "127.0.0.1 epimodel.local" | sudo tee -a /etc/hosts
```

Apoi:
- Aplicație: <http://epimodel.local:8080/>
- API direct: <http://epimodel.local:8080/api/health>
- YugabyteDB UI (port-forward separat):
  ```bash
  kubectl port-forward -n epimodel svc/yb-master-ui 7000:7000
  # → http://localhost:7000
  ```

Pe un cluster cu provider LB funcțional, schimbă `ingress-nginx-controller` în `type: LoadBalancer`, mapează `EXTERNAL-IP` în `/etc/hosts` și renunță la port-forward.

## Operațiuni comune

```bash
# Scalează runner-ul Python la 3 replici
kubectl scale -n epimodel deploy/runner-python --replicas=3

# Reîncarcă API-ul după push imagine nouă
kubectl rollout restart deploy/api -n epimodel

# Loguri live
kubectl logs -f -n epimodel deploy/runner-julia

# Re-rulează migrațiile
kubectl delete job db-migrate -n epimodel
kubectl create configmap db-migrations -n epimodel \
  --from-file=../db/migrations/ \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f 30-migrate-job.yaml

# Conectare directă la YSQL
kubectl exec -it -n epimodel yb-tserver-0 -- \
  ysqlsh -h yb-tserver-service -U yugabyte -d yugabyte
```

## Cleanup

```bash
# Sterge aplicatia, pastreaza datele YugabyteDB
kubectl delete -f 70-ingress.yaml
kubectl delete -f 60-frontend.yaml
kubectl delete -f 52-runner-julia.yaml -f 51-runner-r.yaml -f 50-runner-python.yaml
kubectl delete -f 40-api.yaml
kubectl delete -f 30-migrate-job.yaml
kubectl delete configmap db-migrations -n epimodel
kubectl delete -f 20-redis.yaml

# Cleanup complet (inclusiv volume persistente)
helm uninstall yugabyte -n epimodel
kubectl delete pvc -n epimodel -l app.kubernetes.io/name=yb-master
kubectl delete pvc -n epimodel -l app.kubernetes.io/name=yb-tserver
kubectl delete namespace epimodel
```

## Sizing — note pentru cluster mic

Workerii `kube-4kdhb` au doar 2 vCPU și 4 GiB RAM fiecare. Valorile setate sunt pentru un profil **PoC / demonstrativ**, nu producție:

| Componentă | replici | CPU req | RAM req |
|---|---|---|---|
| yb-master | 3 | 100m | 512Mi |
| yb-tserver | 3 | 200m | 1Gi |
| redis | 1 | 50m | 64Mi |
| api | 2 | 100m | 64Mi |
| runner-python | 1 | 200m | 256Mi |
| runner-r | 1 | 200m | 256Mi |
| runner-julia | 1 | 200m | 384Mi |
| frontend | 1 | 50m | 32Mi |
| ingress-nginx | 1 | 50m | 128Mi |
| metrics-server | 1 | 20m | 64Mi |

Total requests: ≈ 1.5 vCPU, ~3.8 GiB → confortabil în 6 vCPU / ~11.5 GiB total pe workeri.

## Observații pentru un deployment real

- **Parolă YugabyteDB:** default `yugabyte:yugabyte`. Rotește cu `ALTER USER yugabyte PASSWORD '...'` și actualizează Secret-ul.
- **TLS la Ingress:** lipsește pentru simplitate. Adaugă cert-manager + Let's Encrypt sau un cert autosigned.
- **NetworkPolicy:** nu sunt definite. Pentru zero-trust, restricționează API → DB/Redis, Runner → DB/Redis, Frontend → API.
- **Backup YugabyteDB:** `yb-admin` snapshots sau replicare cross-cluster.
- **HPA:** activabil pe runnere (după metric custom `redis_queue_length` via KEDA) după ce metrics-server e instalat.
