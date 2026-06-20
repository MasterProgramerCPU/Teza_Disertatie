<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useBenchmarksStore } from "@/stores/benchmarks.store";
import { MODEL_LABELS } from "@/model-presets";
import type { Language, ModelType } from "@/types";
import BenchmarkHistogram from "@/components/BenchmarkHistogram.vue";
import BenchmarkScalingChart from "@/components/BenchmarkScalingChart.vue";

const props = defineProps<{ model: string; language: string }>();

const benchmarks = useBenchmarksStore();

const modelType = computed(() => props.model as ModelType);
const language = computed(() => props.language as Language);

async function reload() {
  await benchmarks.fetchRuns(modelType.value, language.value);
}

onMounted(reload);
watch(() => [props.model, props.language], reload);

interface Stats {
  n: number;
  min: number;
  max: number;
  mean: number;
  median: number;
  q1: number;
  q3: number;
  iqr: number;
  std: number;
}

function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (pos - lo) * (sorted[hi] - sorted[lo]);
}

function stats(values: number[]): Stats {
  if (values.length === 0) {
    return { n: 0, min: 0, max: 0, mean: 0, median: 0, q1: 0, q3: 0, iqr: 0, std: 0 };
  }
  const s = [...values].sort((a, b) => a - b);
  const n = s.length;
  const mean = s.reduce((a, b) => a + b, 0) / n;
  const variance = s.reduce((a, x) => a + (x - mean) ** 2, 0) / n;
  const q1 = quantile(s, 0.25);
  const q3 = quantile(s, 0.75);
  return {
    n,
    min: s[0],
    max: s[n - 1],
    mean,
    median: quantile(s, 0.5),
    q1, q3,
    iqr: q3 - q1,
    std: Math.sqrt(variance),
  };
}

const wallStats = computed(() => stats(benchmarks.runs.map((r) => r.wall_time_ms)));
const cpuStats = computed(() => stats(benchmarks.runs.map((r) => r.cpu_time_ms)));
const memStats = computed(() => stats(benchmarks.runs.map((r) => r.peak_memory_mb)));

const wallValues = computed(() => benchmarks.runs.map((r) => r.wall_time_ms));
const memValues = computed(() => benchmarks.runs.map((r) => r.peak_memory_mb));

const scalingPoints = computed(() =>
  benchmarks.runs.map((r) => ({ t_max: r.t_max, wall_ms: r.wall_time_ms })),
);

const distinctTmax = computed(
  () => new Set(benchmarks.runs.map((r) => r.t_max)).size,
);

function fmtMs(v: number): string {
  if (v >= 1000) return (v / 1000).toFixed(2) + " s";
  return v.toFixed(0) + " ms";
}
function fmtMB(v: number): string { return v.toFixed(1) + " MB"; }
function fmtDate(s?: string): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("ro-RO", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}
function durationMs(a: string, b?: string): string {
  if (!b) return "—";
  const ms = new Date(b).getTime() - new Date(a).getTime();
  return fmtMs(ms);
}
</script>

<template>
  <div class="row" style="align-items: baseline; gap: 0.75rem;">
    <router-link :to="{ name: 'benchmarks' }">← Înapoi la benchmarks</router-link>
  </div>

  <h1>
    Benchmark: <strong>{{ MODEL_LABELS[modelType] ?? modelType }}</strong>
    <span class="muted"> × </span>
    <strong>{{ language }}</strong>
  </h1>
  <p class="muted">
    Detaliu pentru toate rulările finalizate ale combinației
    {{ MODEL_LABELS[modelType] ?? modelType }} / {{ language }} în studiul curent.
  </p>

  <p v-if="benchmarks.loading" class="muted">Se încarcă…</p>
  <p v-if="benchmarks.error" class="alert error">{{ benchmarks.error }}</p>

  <template v-if="!benchmarks.loading && benchmarks.runs.length === 0 && !benchmarks.error">
    <div class="card">
      <p class="muted">Nicio rulare finalizată pentru această combinație.</p>
    </div>
  </template>

  <template v-if="benchmarks.runs.length > 0">
    <!-- ============== STATISTICI ============== -->
    <section class="card">
      <h2>Statistici</h2>
      <p class="muted small">
        Calculate pe cele {{ wallStats.n }} rulări finalizate. Quartilele folosesc
        interpolare liniară; IQR = Q3 − Q1; deviația standard este populațională.
      </p>

      <div class="stat-grid">
        <div class="stat-block">
          <div class="stat-title">Wall-time</div>
          <table class="stat-tbl">
            <tr><td>n</td><th>{{ wallStats.n }}</th></tr>
            <tr><td>mediana</td><th>{{ fmtMs(wallStats.median) }}</th></tr>
            <tr><td>media</td><th>{{ fmtMs(wallStats.mean) }}</th></tr>
            <tr><td>std</td><th>{{ fmtMs(wallStats.std) }}</th></tr>
            <tr><td>min</td><th>{{ fmtMs(wallStats.min) }}</th></tr>
            <tr><td>max</td><th>{{ fmtMs(wallStats.max) }}</th></tr>
            <tr><td>Q1</td><th>{{ fmtMs(wallStats.q1) }}</th></tr>
            <tr><td>Q3</td><th>{{ fmtMs(wallStats.q3) }}</th></tr>
            <tr><td>IQR</td><th>{{ fmtMs(wallStats.iqr) }}</th></tr>
          </table>
        </div>

        <div class="stat-block">
          <div class="stat-title">CPU-time</div>
          <table class="stat-tbl">
            <tr><td>n</td><th>{{ cpuStats.n }}</th></tr>
            <tr><td>mediana</td><th>{{ fmtMs(cpuStats.median) }}</th></tr>
            <tr><td>media</td><th>{{ fmtMs(cpuStats.mean) }}</th></tr>
            <tr><td>std</td><th>{{ fmtMs(cpuStats.std) }}</th></tr>
            <tr><td>min</td><th>{{ fmtMs(cpuStats.min) }}</th></tr>
            <tr><td>max</td><th>{{ fmtMs(cpuStats.max) }}</th></tr>
            <tr><td>Q1</td><th>{{ fmtMs(cpuStats.q1) }}</th></tr>
            <tr><td>Q3</td><th>{{ fmtMs(cpuStats.q3) }}</th></tr>
            <tr><td>IQR</td><th>{{ fmtMs(cpuStats.iqr) }}</th></tr>
          </table>
        </div>

        <div class="stat-block">
          <div class="stat-title">Memorie peak</div>
          <table class="stat-tbl">
            <tr><td>n</td><th>{{ memStats.n }}</th></tr>
            <tr><td>mediana</td><th>{{ fmtMB(memStats.median) }}</th></tr>
            <tr><td>media</td><th>{{ fmtMB(memStats.mean) }}</th></tr>
            <tr><td>std</td><th>{{ fmtMB(memStats.std) }}</th></tr>
            <tr><td>min</td><th>{{ fmtMB(memStats.min) }}</th></tr>
            <tr><td>max</td><th>{{ fmtMB(memStats.max) }}</th></tr>
            <tr><td>Q1</td><th>{{ fmtMB(memStats.q1) }}</th></tr>
            <tr><td>Q3</td><th>{{ fmtMB(memStats.q3) }}</th></tr>
            <tr><td>IQR</td><th>{{ fmtMB(memStats.iqr) }}</th></tr>
          </table>
        </div>
      </div>
    </section>

    <!-- ============== HISTOGRAMA WALL-TIME ============== -->
    <section class="card">
      <h2>Distribuția wall-time</h2>
      <p class="muted small">
        Histogramă cu {{ Math.max(3, Math.min(Math.ceil(Math.sqrt(wallValues.length)), 20)) }}
        bucket-uri (regula $\sqrt{n}$).
      </p>
      <BenchmarkHistogram :values="wallValues" unit="ms" :height="300" />
    </section>

    <!-- ============== HISTOGRAMA MEMORIE (daca variabila) ============== -->
    <section v-if="memStats.max - memStats.min > 0.5" class="card">
      <h2>Distribuția memoriei peak</h2>
      <BenchmarkHistogram :values="memValues" unit="MB" :height="260" />
    </section>

    <!-- ============== SCALING ============== -->
    <section v-if="distinctTmax >= 2" class="card">
      <h2>Scalare wall-time în funcție de t<sub>max</sub></h2>
      <p class="muted small">
        Pentru fiecare t<sub>max</sub> distinct, mediana (linie continuă) plus
        minimul și maximul ca repere. Axa Y este logaritmică.
      </p>
      <BenchmarkScalingChart :points="scalingPoints" :height="340" />
    </section>
    <section v-else class="card">
      <h2>Scalare wall-time</h2>
      <p class="muted">
        Pentru această combinație există doar valoarea
        t<sub>max</sub> = {{ benchmarks.runs[0]?.t_max }}. Pentru a vedea un grafic de
        scalare, rulează aceeași combinație și pentru alte orizonturi.
      </p>
    </section>

    <!-- ============== TABEL DE RULARI ============== -->
    <section class="card">
      <h2>Rulări individuale ({{ benchmarks.runs.length }})</h2>
      <p class="muted small">
        Ordonate cronologic descrescător. Click pe ID-ul rulării pentru graficul ei.
      </p>
      <table>
        <thead>
          <tr>
            <th>Rulare</th>
            <th>Dataset</th>
            <th>t<sub>max</sub></th>
            <th>Wall</th>
            <th>CPU</th>
            <th>Memorie</th>
            <th>Pornită</th>
            <th>Durată end-to-end</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in benchmarks.runs" :key="r.simulation_id">
            <td>
              <router-link :to="{ name: 'simulation-detail', params: { id: r.simulation_id } }">
                {{ r.simulation_id.slice(0, 8) }}…
              </router-link>
            </td>
            <td>{{ r.dataset_name }}</td>
            <td>{{ r.t_max }}</td>
            <td>{{ fmtMs(r.wall_time_ms) }}</td>
            <td>{{ fmtMs(r.cpu_time_ms) }}</td>
            <td>{{ fmtMB(r.peak_memory_mb) }}</td>
            <td>{{ fmtDate(r.created_at) }}</td>
            <td>{{ durationMs(r.created_at, r.completed_at) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </template>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  margin-top: 0.5rem;
}
.stat-block {
  border: 1px solid var(--c-border);
  padding: 0.6rem 0.8rem;
  background: var(--c-surface-soft);
  color: var(--c-text);
}
.stat-title {
  font-weight: 600;
  margin-bottom: 0.3rem;
}
.stat-tbl {
  width: 100%;
  font-size: 0.92rem;
}
.stat-tbl td { color: var(--c-text-muted); padding: 1px 0; }
.stat-tbl th { text-align: right; font-weight: 500; padding: 1px 0; }
.small { font-size: 0.85rem; }
section.card { margin-bottom: 1rem; }
</style>
