<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRoute } from "vue-router";
import { api } from "@/api/client";
import type {
  BenchmarkAggregate,
  Dataset,
  Simulation,
  Study,
  StudyMember,
} from "@/types";

const route = useRoute();
const studyId = route.params.id as string;

const study = ref<Study | null>(null);
const members = ref<StudyMember[]>([]);
const datasets = ref<Dataset[]>([]);
const simulations = ref<Simulation[]>([]);
const benchmarks = ref<BenchmarkAggregate[]>([]);
const error = ref<string | null>(null);
const loading = ref(true);

const totalRecords = computed(() =>
  datasets.value.reduce((sum, d) => sum + (d.record_count ?? 0), 0),
);

function fmt(n: number): string {
  return n.toLocaleString("ro-RO");
}
function fmtDate(s: string): string {
  return new Date(s).toLocaleString("ro-RO");
}

onMounted(async () => {
  try {
    const [s, m, d, si, b] = await Promise.all([
      api.get<Study>(`/studies/${studyId}`),
      api.get<StudyMember[] | null>(`/studies/${studyId}/members`),
      api.get<Dataset[] | null>(`/studies/${studyId}/datasets`),
      api.get<Simulation[] | null>(`/studies/${studyId}/simulations`),
      api.get<BenchmarkAggregate[] | null>(`/studies/${studyId}/benchmarks`),
    ]);
    study.value = s;
    members.value = m ?? [];
    datasets.value = d ?? [];
    simulations.value = si ?? [];
    benchmarks.value = b ?? [];
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <p>
    <router-link to="/studies">← Înapoi la lista de studii</router-link>
  </p>

  <p v-if="error" class="error">{{ error }}</p>
  <p v-if="loading && !error" class="muted">Se încarcă…</p>

  <template v-if="study">
    <h1>{{ study.name }}</h1>
    <p class="muted">
      <code>{{ study.disease_code }}</code>
      &middot; creat {{ fmtDate(study.created_at) }}
      <span v-if="study.updated_at && study.updated_at !== study.created_at">
        &middot; actualizat {{ fmtDate(study.updated_at) }}
      </span>
    </p>
    <p v-if="study.description" class="description">{{ study.description }}</p>

    <div class="grid">
      <div class="metric">
        <div class="value">{{ fmt(members.length) }}</div>
        <div class="label">Membri</div>
      </div>
      <div class="metric">
        <div class="value">{{ fmt(datasets.length) }}</div>
        <div class="label">Seturi de date</div>
        <div class="sub">{{ fmt(totalRecords) }} înregistrări totale</div>
      </div>
      <div class="metric">
        <div class="value">{{ fmt(simulations.length) }}</div>
        <div class="label">Simulări lansate</div>
      </div>
      <div class="metric">
        <div class="value">{{ fmt(benchmarks.length) }}</div>
        <div class="label">Combinații model × limbaj</div>
        <div class="sub">cu rulări complete</div>
      </div>
    </div>

    <div class="card">
      <h2>Membri</h2>
      <p v-if="members.length === 0" class="muted">Niciun membru.</p>
      <table v-else>
        <thead>
          <tr><th>Email</th><th>Rol</th><th>Adăugat</th></tr>
        </thead>
        <tbody>
          <tr v-for="m in members" :key="m.user_id">
            <td>{{ m.email || m.user_id }}</td>
            <td><code>{{ m.role }}</code></td>
            <td class="muted">{{ fmtDate(m.joined_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>Seturi de date</h2>
      <p v-if="datasets.length === 0" class="muted">Niciun set de date încărcat.</p>
      <table v-else>
        <thead>
          <tr>
            <th>Nume</th><th>Cod boală</th><th>Înregistrări</th><th>Încărcat</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in datasets" :key="d.id">
            <td><strong>{{ d.name }}</strong></td>
            <td><code>{{ d.disease_code }}</code></td>
            <td class="num">{{ fmt(d.record_count) }}</td>
            <td class="muted">{{ fmtDate(d.uploaded_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>Simulări</h2>
      <p v-if="simulations.length === 0" class="muted">Nicio simulare lansată.</p>
      <table v-else>
        <thead>
          <tr>
            <th>Status</th><th>Model</th><th>Limbaj</th><th>t_max</th>
            <th>Creată</th><th>Finalizată</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in simulations" :key="s.id">
            <td><span :class="['badge', `status-${s.status}`]">{{ s.status }}</span></td>
            <td><code>{{ s.model_type }}</code></td>
            <td><code>{{ s.language }}</code></td>
            <td class="num">{{ fmt(s.t_max) }}</td>
            <td class="muted">{{ fmtDate(s.created_at) }}</td>
            <td class="muted">{{ s.completed_at ? fmtDate(s.completed_at) : "—" }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h2>Benchmarks (agregate)</h2>
      <p v-if="benchmarks.length === 0" class="muted">
        Niciun benchmark disponibil — necesită simulări <code>completed</code>.
      </p>
      <table v-else>
        <thead>
          <tr>
            <th>Model</th><th>Limbaj</th><th>Rulări</th>
            <th>Wall median (ms)</th><th>Wall p95 (ms)</th>
            <th>CPU median (ms)</th><th>Memorie median (MB)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(b, i) in benchmarks" :key="i">
            <td><code>{{ b.model_type }}</code></td>
            <td><code>{{ b.language }}</code></td>
            <td class="num">{{ fmt(b.run_count) }}</td>
            <td class="num">{{ fmt(Math.round(b.median_wall_ms)) }}</td>
            <td class="num">{{ fmt(Math.round(b.p95_wall_ms)) }}</td>
            <td class="num">{{ fmt(Math.round(b.median_cpu_ms)) }}</td>
            <td class="num">{{ b.median_memory_mb.toFixed(1) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </template>
</template>

<style scoped>
.description {
  margin: 8px 0 18px;
  padding: 10px 12px;
  background: var(--c-surface-soft);
  border-left: 3px solid var(--c-accent);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.metric {
  background: linear-gradient(180deg, #f8f6ed 0%, #ece9d8 100%);
  border: 1px solid var(--c-border-dark);
  padding: 14px;
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #808080, var(--shadow-sm);
}
.value { font-size: 22px; font-weight: 700; color: var(--c-primary); line-height: 1.1; text-shadow: 1px 1px 0 #ffffff; }
.label { margin-top: 4px; font-weight: 500; }
.sub   { margin-top: 6px; font-size: 11px; color: var(--c-text-muted); }
.num   { text-align: right; font-variant-numeric: tabular-nums; }
.badge {
  display: inline-block;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid #404040;
  text-transform: uppercase;
}
.status-completed { background: #c6e7c6; color: #1f5f1f; border-color: #1f5f1f; }
.status-running   { background: #fff2a8; color: #6a5a00; border-color: #6a5a00; }
.status-pending   { background: #d0d0d0; color: #303030; border-color: #404040; }
.status-failed    { background: #f5c6c6; color: #7a0000; border-color: #7a0000; }
</style>
