<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useAdminStore } from "@/stores/admin.store";

const admin = useAdminStore();
const limit = ref(30);

async function reload() {
  await admin.fetchRecent(limit.value);
}

onMounted(reload);

function fmtDate(s: string): string {
  return new Date(s).toLocaleString("ro-RO");
}
function fmt(n: number): string {
  return n.toLocaleString("ro-RO");
}
</script>

<template>
  <h1>Activitate recentă</h1>
  <p class="muted">
    Cele mai recente simulări și încărcări de seturi de date, cross-studiu.
  </p>

  <div class="filter-bar">
    <label>
      Câte intrări:
      <select v-model.number="limit" @change="reload">
        <option :value="20">20</option>
        <option :value="50">50</option>
        <option :value="100">100</option>
        <option :value="200">200</option>
      </select>
    </label>
    <button @click="reload" :disabled="admin.loading">
      {{ admin.loading ? "Se încarcă…" : "Reîmprospătează" }}
    </button>
  </div>

  <p v-if="admin.error" class="error">{{ admin.error }}</p>

  <div class="card">
    <h2>Simulări recente ({{ admin.recentSimulations.length }})</h2>
    <p v-if="admin.recentSimulations.length === 0" class="muted">Nicio simulare lansată.</p>
    <table v-else>
      <thead>
        <tr>
          <th>Status</th><th>Studiu</th><th>Lansat de</th>
          <th>Model</th><th>Limbaj</th><th>t_max</th>
          <th>Creat</th><th>Finalizat</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in admin.recentSimulations" :key="s.id">
          <td><span :class="['badge', `status-${s.status}`]">{{ s.status }}</span></td>
          <td><router-link :to="`/studies/${s.study_id}`">{{ s.study_name }}</router-link></td>
          <td class="muted">{{ s.user_email }}</td>
          <td><code>{{ s.model_type }}</code></td>
          <td><code>{{ s.language }}</code></td>
          <td class="num">{{ fmt(s.t_max) }}</td>
          <td class="muted nowrap">{{ fmtDate(s.created_at) }}</td>
          <td class="muted nowrap">{{ s.completed_at ? fmtDate(s.completed_at) : "—" }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>Seturi de date recente ({{ admin.recentDatasets.length }})</h2>
    <p v-if="admin.recentDatasets.length === 0" class="muted">Niciun set de date încărcat.</p>
    <table v-else>
      <thead>
        <tr>
          <th>Nume</th><th>Studiu</th><th>Încărcat de</th>
          <th>Boală</th><th>Înregistrări</th><th>Încărcat</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in admin.recentDatasets" :key="d.id">
          <td><strong>{{ d.name }}</strong></td>
          <td><router-link :to="`/studies/${d.study_id}`">{{ d.study_name }}</router-link></td>
          <td class="muted">{{ d.user_email }}</td>
          <td><code>{{ d.disease_code }}</code></td>
          <td class="num">{{ fmt(d.record_count) }}</td>
          <td class="muted nowrap">{{ fmtDate(d.uploaded_at) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 12px 0;
}
.num { text-align: right; font-variant-numeric: tabular-nums; }
.nowrap { white-space: nowrap; }
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
