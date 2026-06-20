<script setup lang="ts">
import { onMounted, computed } from "vue";
import { useDatasetsStore } from "@/stores/datasets.store";
import { useSimulationsStore } from "@/stores/simulations.store";
import SimulationStatus from "@/components/SimulationStatus.vue";
import { MODEL_LABELS } from "@/model-presets";

const datasets = useDatasetsStore();
const simulations = useSimulationsStore();

onMounted(async () => {
  await Promise.all([datasets.fetchAll(), simulations.fetchAll()]);
});

const recentSimulations = computed(() => simulations.items.slice(0, 5));
const statusCounts = computed(() => {
  const counts: Record<string, number> = { pending: 0, running: 0, completed: 0, failed: 0 };
  for (const s of simulations.items) counts[s.status] = (counts[s.status] ?? 0) + 1;
  return counts;
});
</script>

<template>
  <h1>Dashboard</h1>

  <div class="row" style="margin-bottom: 24px;">
    <div class="card flex-1 metric">
      <div class="muted">Seturi de date</div>
      <div class="metric-value">{{ datasets.items.length }}</div>
    </div>
    <div class="card flex-1 metric">
      <div class="muted">Simulări totale</div>
      <div class="metric-value">{{ simulations.items.length }}</div>
    </div>
    <div class="card flex-1 metric">
      <div class="muted">În execuție</div>
      <div class="metric-value">{{ statusCounts.running + statusCounts.pending }}</div>
    </div>
    <div class="card flex-1 metric">
      <div class="muted">Finalizate</div>
      <div class="metric-value">{{ statusCounts.completed }}</div>
    </div>
  </div>

  <div class="card">
    <h2>Simulări recente</h2>
    <table v-if="recentSimulations.length > 0">
      <thead>
        <tr><th>Status</th><th>Model</th><th>Limbaj</th><th>t_max</th><th>Creată</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="s in recentSimulations" :key="s.id">
          <td><SimulationStatus :status="s.status" /></td>
          <td>{{ MODEL_LABELS[s.model_type] }}</td>
          <td>{{ s.language }}</td>
          <td>{{ s.t_max }}</td>
          <td>{{ new Date(s.created_at).toLocaleString() }}</td>
          <td><router-link :to="`/simulations/${s.id}`">vezi →</router-link></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">Nicio simulare încă. <router-link to="/simulations/new">Pornește una</router-link>.</p>
  </div>
</template>

<style scoped>
.metric {
  min-width: 160px;
  background: linear-gradient(180deg, var(--c-surface-soft) 0%, var(--c-surface) 100%);
  color: var(--c-text);
}
.metric-value {
  margin-top: 6px;
  font-size: 30px;
  font-weight: 700;
  color: var(--c-primary);
  text-shadow: 1px 1px 0 var(--c-border-light);
}
</style>
