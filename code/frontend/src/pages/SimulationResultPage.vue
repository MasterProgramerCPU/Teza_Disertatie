<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useSimulationsStore } from "@/stores/simulations.store";
import SimulationStatus from "@/components/SimulationStatus.vue";
import SIRChart from "@/components/SIRChart.vue";
import type { SimulationResultPoint, SimulationRun } from "@/types";

const props = defineProps<{ id: string }>();
const simulations = useSimulationsStore();

const run = ref<SimulationRun | null>(null);
const points = ref<SimulationResultPoint[]>([]);
const error = ref<string | null>(null);
let cancelled = false;

async function load() {
  try {
    run.value = await simulations.get(props.id);
    if (run.value.status === "completed") {
      points.value = await simulations.results(props.id);
    }
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function startPolling() {
  if (!run.value) return;
  if (run.value.status === "completed" || run.value.status === "failed") return;
  try {
    const final = await simulations.pollUntilDone(props.id, (r) => {
      if (!cancelled) run.value = r;
    });
    if (cancelled) return;
    run.value = final;
    if (final.status === "completed") {
      points.value = await simulations.results(props.id);
    }
  } catch (e) {
    if (!cancelled) error.value = (e as Error).message;
  }
}

onMounted(async () => {
  await load();
  if (!cancelled) await startPolling();
});

onUnmounted(() => { cancelled = true; });

async function downloadCSV() {
  if (!run.value) return;
  const blob = await simulations.exportCSV(run.value.id);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `simulation_${run.value.id}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <p v-if="error" class="alert error">{{ error }}</p>

  <div v-if="run">
    <div class="row" style="justify-content: space-between; margin-bottom: 16px;">
      <h1 style="margin-bottom: 0;">Simulare</h1>
      <SimulationStatus :status="run.status" />
    </div>

    <div class="card">
      <dl class="meta">
        <dt>ID</dt><dd><code>{{ run.id }}</code></dd>
        <dt>Limbaj</dt><dd>{{ run.language }}</dd>
        <dt>β</dt><dd>{{ run.beta }}</dd>
        <dt>γ</dt><dd>{{ run.gamma }}</dd>
        <dt>R<sub>0</sub></dt><dd>{{ (run.beta / run.gamma).toFixed(2) }}</dd>
        <dt>Populație N</dt><dd>{{ run.population_n.toLocaleString() }}</dd>
        <dt>t_max</dt><dd>{{ run.t_max }} zile</dd>
        <dt>Creată</dt><dd>{{ new Date(run.created_at).toLocaleString() }}</dd>
        <dt v-if="run.completed_at">Finalizată</dt>
        <dd v-if="run.completed_at">{{ new Date(run.completed_at).toLocaleString() }}</dd>
        <template v-if="run.error_message">
          <dt>Eroare</dt><dd class="error">{{ run.error_message }}</dd>
        </template>
      </dl>
    </div>

    <div v-if="run.status === 'completed' && points.length > 0" class="card">
      <div class="row" style="justify-content: space-between; margin-bottom: 16px;">
        <h2 style="margin-bottom: 0;">Traiectoriile S/I/R</h2>
        <button @click="downloadCSV">Export CSV</button>
      </div>
      <SIRChart :series="[{ label: 'S/I/R', points }]" />
    </div>

    <div v-else-if="run.status === 'pending' || run.status === 'running'" class="alert info">
      Simularea încă rulează. Pagina se actualizează automat la finalizare.
    </div>
  </div>
</template>

<style scoped>
.meta { display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; }
.meta dt { font-weight: 500; color: var(--c-text-muted); }
.meta dd { margin: 0; }
</style>
