<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { useStudiesStore } from "@/stores/studies.store";
import type {
  BenchmarkAggregate,
  Dataset,
  Study,
  StudyMember,
  SimulationRun,
} from "@/types";
import UserAvatar from "@/components/UserAvatar.vue";

const router = useRouter();
const studies = useStudiesStore();

const study = ref<Study | null>(null);
const members = ref<StudyMember[]>([]);
const datasets = ref<Dataset[]>([]);
const simulations = ref<SimulationRun[]>([]);
const benchmarks = ref<BenchmarkAggregate[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

const studyId = computed(() => studies.currentStudyId);
const isAdmin = computed(() => studies.currentRole === "admin");

const totalRecords = computed(() =>
  datasets.value.reduce((sum, d) => sum + (d.record_count ?? 0), 0),
);

const modelLanguageCombos = computed(() => {
  const seen = new Set<string>();
  for (const s of simulations.value) {
    if (s.status === "completed") {
      seen.add(`${s.model_type}/${s.language}`);
    }
  }
  return seen.size;
});

// Breakdowns (calculate clientside, study-scoped)
function tally<T extends Record<string, unknown>>(items: T[], key: keyof T): Array<{ value: string; count: number }> {
  const map = new Map<string, number>();
  for (const it of items) {
    const v = String(it[key] ?? "—");
    map.set(v, (map.get(v) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count);
}

const breakdownStatus = computed(() => tally(simulations.value, "status"));
const breakdownModel = computed(() => tally(simulations.value, "model_type"));
const breakdownLanguage = computed(() => tally(simulations.value, "language"));

const maxStatus = computed(() => Math.max(1, ...breakdownStatus.value.map((b) => b.count)));
const maxModel = computed(() => Math.max(1, ...breakdownModel.value.map((b) => b.count)));
const maxLanguage = computed(() => Math.max(1, ...breakdownLanguage.value.map((b) => b.count)));

// Activity = ultimele 15 simulări + ultimele 10 dataset uploads, în ordinea timpului
type ActivityEntry =
  | { kind: "simulation"; at: string; sim: SimulationRun }
  | { kind: "dataset"; at: string; ds: Dataset };

const activity = computed<ActivityEntry[]>(() => {
  const out: ActivityEntry[] = [];
  for (const s of simulations.value) {
    out.push({ kind: "simulation", at: s.created_at, sim: s });
  }
  for (const d of datasets.value) {
    out.push({ kind: "dataset", at: d.uploaded_at, ds: d });
  }
  out.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
  return out.slice(0, 25);
});

function fmt(n: number): string {
  return n.toLocaleString("ro-RO");
}
function fmtDate(s: string): string {
  return new Date(s).toLocaleString("ro-RO");
}

async function load() {
  loading.value = true;
  error.value = null;
  if (!studies.memberships.length) await studies.fetchMine();
  if (!studyId.value) {
    error.value = "Nu există un studiu selectat";
    loading.value = false;
    return;
  }
  try {
    const [s, m, d, si, b] = await Promise.all([
      api.get<Study>(`/studies/${studyId.value}`),
      api.get<StudyMember[] | null>(`/studies/${studyId.value}/members`),
      api.get<Dataset[] | null>(`/studies/${studyId.value}/datasets`),
      api.get<SimulationRun[] | null>(`/studies/${studyId.value}/simulations`),
      api.get<BenchmarkAggregate[] | null>(`/studies/${studyId.value}/benchmarks`),
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
}

onMounted(load);
</script>

<template>
  <div class="page">
    <h1>Panou administrator de studiu</h1>

    <p v-if="!isAdmin && !loading" class="muted">
      Această pagină e disponibilă doar pentru rolul <code>admin</code> al studiului.
      Rolul curent: <code>{{ studies.currentRole ?? "—" }}</code>.
    </p>

    <p v-if="error" class="alert error">{{ error }}</p>
    <p v-if="loading && !error" class="muted">Se încarcă…</p>

    <template v-if="isAdmin && study">
      <p class="muted">
        <strong>{{ study.name }}</strong>
        &middot; <code>{{ study.disease_code }}</code>
        &middot; creat {{ fmtDate(study.created_at) }}
      </p>
      <p v-if="study.description" class="description">{{ study.description }}</p>

      <!-- Counters -->
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
          <div class="value">{{ fmt(modelLanguageCombos) }}</div>
          <div class="label">Combinații model × limbaj</div>
          <div class="sub">cu rulări finalizate</div>
        </div>
      </div>

      <!-- Breakdowns -->
      <div class="card">
        <h2>Distribuția simulărilor în studiu</h2>
        <div v-if="simulations.length === 0" class="muted">Nicio simulare încă.</div>

        <div v-else class="bd-grid">
          <div class="bd-col">
            <h3>După status</h3>
            <div class="bd-row" v-for="b in breakdownStatus" :key="'st-' + b.value">
              <span class="bd-lbl">
                <span :class="['pill', `status-${b.value}`]">{{ b.value }}</span>
              </span>
              <span class="bd-bar">
                <span class="bd-fill" :style="{ width: (b.count / maxStatus * 100) + '%' }"></span>
              </span>
              <span class="bd-num">{{ fmt(b.count) }}</span>
            </div>
          </div>

          <div class="bd-col">
            <h3>După model</h3>
            <div class="bd-row" v-for="b in breakdownModel" :key="'mo-' + b.value">
              <span class="bd-lbl"><code>{{ b.value }}</code></span>
              <span class="bd-bar">
                <span class="bd-fill" :style="{ width: (b.count / maxModel * 100) + '%' }"></span>
              </span>
              <span class="bd-num">{{ fmt(b.count) }}</span>
            </div>
          </div>

          <div class="bd-col">
            <h3>După limbaj</h3>
            <div class="bd-row" v-for="b in breakdownLanguage" :key="'la-' + b.value">
              <span class="bd-lbl"><code>{{ b.value }}</code></span>
              <span class="bd-bar">
                <span class="bd-fill" :style="{ width: (b.count / maxLanguage * 100) + '%' }"></span>
              </span>
              <span class="bd-num">{{ fmt(b.count) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Activity feed -->
      <div class="card">
        <h2>Activitate recentă în studiu</h2>
        <p v-if="activity.length === 0" class="muted">Nu există activitate.</p>
        <table v-else>
          <thead>
            <tr><th>Când</th><th>Tip</th><th>Detalii</th></tr>
          </thead>
          <tbody>
            <tr v-for="(a, i) in activity" :key="i">
              <td class="muted nowrap">{{ fmtDate(a.at) }}</td>
              <td>
                <span v-if="a.kind === 'simulation'" class="pill kind-sim">simulare</span>
                <span v-else class="pill kind-ds">set de date</span>
              </td>
              <td v-if="a.kind === 'simulation'">
                <code>{{ a.sim.model_type }}</code> /
                <code>{{ a.sim.language }}</code> ·
                t_max={{ a.sim.t_max }} ·
                <span :class="['pill', `status-${a.sim.status}`]">{{ a.sim.status }}</span>
              </td>
              <td v-else>
                <strong>{{ a.ds.name }}</strong>
                <span class="muted"> · {{ fmt(a.ds.record_count) }} înregistrări</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Members -->
      <div class="card">
        <div class="card-head">
          <h2>Membri ({{ members.length }})</h2>
          <button
            type="button"
            class="btn"
            @click="router.push({ name: 'study-manage', params: { id: studyId } })"
          >
            Gestionează membrii
          </button>
        </div>
        <ul class="members">
          <li v-for="m in members" :key="m.user_id">
            <UserAvatar :user-id="m.user_id" :email="m.email" :size="32" />
            <span class="m-email">{{ m.email || m.user_id }}</span>
            <span :class="['pill', `role-${m.role}`]">{{ m.role }}</span>
            <span class="muted nowrap">{{ fmtDate(m.joined_at) }}</span>
          </li>
        </ul>
      </div>

      <!-- Benchmarks -->
      <div class="card">
        <h2>Benchmark-uri agregate (rulări complete)</h2>
        <p v-if="benchmarks.length === 0" class="muted">
          Niciun benchmark — necesită simulări <code>completed</code>.
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
  </div>
</template>

<style scoped>
.page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 16px;
}
h1 { margin: 0 0 8px; font-size: 20px; color: var(--c-text-strong); }
.muted { color: var(--c-text-muted); }
.description {
  margin: 8px 0 18px;
  padding: 10px 12px;
  background: var(--c-surface-soft);
  color: var(--c-text);
  border-left: 3px solid var(--c-primary);
  font-size: 13px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.metric {
  background: linear-gradient(180deg, var(--c-surface-soft) 0%, var(--c-surface) 100%);
  color: var(--c-text);
  border: 1px solid var(--c-border);
  padding: 14px;
  box-shadow: inset 1px 1px 0 var(--c-border-light), inset -1px -1px 0 var(--c-border-dark);
}
.value {
  font-size: 22px;
  font-weight: 700;
  color: var(--c-primary);
  line-height: 1.1;
  text-shadow: 1px 1px 0 var(--c-border-light);
}
.label { margin-top: 4px; font-weight: 500; font-size: 13px; color: var(--c-text); }
.sub   { margin-top: 4px; font-size: 11px; color: var(--c-text-muted); }
.num   { text-align: right; font-variant-numeric: tabular-nums; }
.nowrap { white-space: nowrap; }

.card {
  background: var(--c-surface);
  color: var(--c-text);
  border: 1px solid var(--c-border-dark);
  box-shadow: inset 1px 1px 0 var(--c-border-light), inset -1px -1px 0 var(--c-border), var(--shadow-sm);
  padding: 14px;
  margin-bottom: 14px;
}
.card h2 {
  margin: 0 0 10px;
  font-size: 14px;
  border-bottom: 1px solid var(--c-border);
  padding-bottom: 6px;
  color: var(--c-text-strong);
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.bd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}
.bd-col h3 { margin: 0 0 6px; font-size: 12px; color: var(--c-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.bd-row {
  display: grid;
  grid-template-columns: 110px 1fr 50px;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  font-size: 12px;
  color: var(--c-text);
}
.bd-lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bd-bar { background: var(--c-surface-dark); height: 12px; border: 1px solid var(--c-border); }
.bd-fill {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--btn-primary-1) 0%, var(--btn-primary-2) 100%);
  transition: width var(--t-slow) var(--easing);
}
.bd-num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; }

table { width: 100%; border-collapse: collapse; font-size: 12px; color: var(--c-text); }
th, td { padding: 5px 8px; text-align: left; border-bottom: 1px dashed var(--c-border); vertical-align: middle; }
th {
  background: linear-gradient(180deg, var(--c-surface-soft) 0%, var(--c-surface-dark) 100%);
  font-weight: 700;
  color: var(--c-text-strong);
}

.btn {
  display: inline-block;
  padding: 4px 10px;
  border: 1px solid var(--btn-border);
  background: linear-gradient(180deg, var(--btn-bg-1) 0%, var(--btn-bg-2) 48%, var(--btn-bg-3) 100%);
  box-shadow: inset 1px 1px 0 var(--btn-inset-light), inset -1px -1px 0 var(--btn-inset-dark);
  color: var(--btn-text);
  font-size: 12px;
  cursor: pointer;
}
.btn:hover { background: linear-gradient(180deg, var(--btn-hover-1) 0%, var(--btn-hover-2) 48%, var(--btn-hover-3) 100%); }

.pill {
  display: inline-block;
  padding: 1px 7px;
  font-size: 10px;
  font-weight: 700;
  border: 1px solid var(--c-border-dark);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.status-completed { background: #c6e7c6; color: #1f5f1f; border-color: #1f5f1f; }
.status-running   { background: #fff2a8; color: #6a5a00; border-color: #6a5a00; }
.status-pending   { background: #d0d0d0; color: #303030; border-color: #404040; }
.status-failed    { background: #f5c6c6; color: #7a0000; border-color: #7a0000; }
.kind-sim  { background: #d6e3ff; color: #0a46c4; border-color: #0a46c4; }
.kind-ds   { background: #e7d6ff; color: #4b1f8c; border-color: #4b1f8c; }
.role-admin       { background: #ffd6a8; color: #6c3a00; border-color: #6c3a00; }
.role-researcher  { background: #d6f0ff; color: #0a3a6c; border-color: #0a3a6c; }
.role-contributor { background: #d6ffd6; color: #1f5f1f; border-color: #1f5f1f; }
.role-viewer      { background: #ececec; color: #404040; border-color: #404040; }

[data-theme="dark"] .status-completed { background: #0f3a18; color: #c8f0d4; border-color: #4ade80; }
[data-theme="dark"] .status-running   { background: #5a4500; color: #fde68a; border-color: #fbbf24; }
[data-theme="dark"] .status-pending   { background: #2a2a2a; color: #c8c8c8; border-color: #5a5a5a; }
[data-theme="dark"] .status-failed    { background: #4a0a0a; color: #fecaca; border-color: #f87171; }
[data-theme="dark"] .kind-sim  { background: #0a3060; color: #cfe6ff; border-color: #6fbcff; }
[data-theme="dark"] .kind-ds   { background: #2a1060; color: #d6c0ff; border-color: #a070ff; }
[data-theme="dark"] .role-admin       { background: #4a2a00; color: #ffd6a8; border-color: #ffae42; }
[data-theme="dark"] .role-researcher  { background: #0a2a4a; color: #cfe6ff; border-color: #6fbcff; }
[data-theme="dark"] .role-contributor { background: #0f3a18; color: #c8f0d4; border-color: #4ade80; }
[data-theme="dark"] .role-viewer      { background: #2a2a2a; color: #c8c8c8; border-color: #5a5a5a; }

.members {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 6px;
}
.members li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px;
  border: 1px solid var(--c-border);
  background: var(--c-surface-soft);
  color: var(--c-text);
}
.m-email { flex: 1; font-size: 12px; overflow: hidden; text-overflow: ellipsis; color: var(--c-text); }

.alert.error {
  background: rgba(176, 0, 0, 0.18);
  border: 1px solid var(--c-danger);
  padding: 6px 10px;
  font-size: 12px;
  color: var(--c-danger);
}
</style>
