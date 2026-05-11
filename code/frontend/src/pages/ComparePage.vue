<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useSimulationsStore } from "@/stores/simulations.store";
import SIRChart from "@/components/SIRChart.vue";
import type { SimulationResultPoint, SimulationRun } from "@/types";

const simulations = useSimulationsStore();

const selected = ref<string[]>([]);
const series = ref<{ label: string; points: SimulationResultPoint[]; style: "solid" | "dashed" | "dotted" }[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const completedRuns = computed(() =>
  simulations.items.filter((r) => r.status === "completed"),
);

onMounted(async () => {
  if (simulations.items.length === 0) await simulations.fetchAll();
});

function toggle(id: string) {
  const i = selected.value.indexOf(id);
  if (i >= 0) selected.value.splice(i, 1);
  else if (selected.value.length < 3) selected.value.push(id);
}

const STYLES: Array<"solid" | "dashed" | "dotted"> = ["solid", "dashed", "dotted"];

async function compare() {
  if (selected.value.length < 2) {
    error.value = "selectează 2-3 simulări";
    return;
  }
  error.value = null;
  loading.value = true;
  try {
    const results = await Promise.all(
      selected.value.map((id) => simulations.results(id)),
    );
    const runs: SimulationRun[] = await Promise.all(
      selected.value.map((id) => simulations.get(id)),
    );
    series.value = results.map((points, idx) => ({
      label: runs[idx].language,
      points,
      style: STYLES[idx % STYLES.length],
    }));
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <h1>Comparare simulări</h1>
  <p class="muted">Selectează 2-3 simulări finalizate (de preferat pe același set de date și aceiași β/γ).</p>

  <div class="card">
    <table v-if="completedRuns.length > 0">
      <thead>
        <tr><th></th><th>Limbaj</th><th>β</th><th>γ</th><th>t_max</th><th>Dataset</th><th>Finalizat</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in completedRuns" :key="s.id">
          <td>
            <input
              type="checkbox"
              :checked="selected.includes(s.id)"
              @change="toggle(s.id)"
              :disabled="!selected.includes(s.id) && selected.length >= 3"
              style="width: auto;"
            />
          </td>
          <td>{{ s.language }}</td>
          <td>{{ s.beta.toFixed(4) }}</td>
          <td>{{ s.gamma.toFixed(4) }}</td>
          <td>{{ s.t_max }}</td>
          <td><code>{{ s.dataset_id.slice(0, 8) }}…</code></td>
          <td>{{ s.completed_at ? new Date(s.completed_at).toLocaleString() : "—" }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">Nicio simulare finalizată încă.</p>

    <button class="primary" @click="compare" :disabled="loading || selected.length < 2" style="margin-top: 12px;">
      {{ loading ? "Se încarcă..." : "Compară" }}
    </button>
    <p v-if="error" class="alert error" style="margin-top: 12px;">{{ error }}</p>
  </div>

  <div v-if="series.length > 0" class="card">
    <h2>Comparație</h2>
    <SIRChart :series="series" :height="500" />
  </div>
</template>
