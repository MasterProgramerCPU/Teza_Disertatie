<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useDatasetsStore } from "@/stores/datasets.store";
import { useSimulationsStore } from "@/stores/simulations.store";
import { useStudiesStore } from "@/stores/studies.store";
import ParameterForm from "@/components/ParameterForm.vue";
import { defaultParameters } from "@/model-presets";
import type { Language, ModelType } from "@/types";

const route = useRoute();
const router = useRouter();
const datasets = useDatasetsStore();
const simulations = useSimulationsStore();
const studies = useStudiesStore();

const datasetId = ref<string>((route.query.dataset_id as string) ?? "");
const params = ref<{
  model_type: ModelType;
  parameters: Record<string, number>;
  t_max: number;
  language: Language;
}>({
  model_type: "sidarthe",
  parameters: defaultParameters("sidarthe"),
  t_max: 365,
  language: "python",
});
const submitting = ref(false);
const error = ref<string | null>(null);

onMounted(async () => {
  if (datasets.items.length === 0) await datasets.fetchAll();
  if (!datasetId.value && datasets.items.length > 0) {
    datasetId.value = datasets.items[0].id;
  }
});

async function submit() {
  if (!datasetId.value) {
    error.value = "alege un set de date";
    return;
  }
  error.value = null;
  submitting.value = true;
  try {
    const run = await simulations.create({
      dataset_id: datasetId.value,
      model_type: params.value.model_type,
      language: params.value.language,
      parameters: params.value.parameters,
      t_max: params.value.t_max,
    });
    router.push({ name: "simulation-detail", params: { id: run.id } });
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <h1>Simulare nouă</h1>

  <div v-if="!studies.canWriteSimulations" class="card">
    <p class="alert info">
      Rolul tău (<strong>{{ studies.currentRole }}</strong>) nu permite lansarea de simulări.
      Doar administratorii și cercetătorii pot crea simulări noi.
    </p>
  </div>

  <div v-else class="card">
    <form @submit.prevent="submit">
      <div class="col">
        <div>
          <label>Set de date</label>
          <select v-model="datasetId" :disabled="submitting" required>
            <option value="" disabled>— alege —</option>
            <option v-for="d in datasets.items" :key="d.id" :value="d.id">
              {{ d.name }} ({{ d.record_count }} înregistrări)
            </option>
          </select>
        </div>

        <ParameterForm v-model="params" :disabled="submitting" />

        <p v-if="error" class="alert error">{{ error }}</p>
        <p v-if="datasets.items.length === 0" class="alert info">
          Nu ai seturi de date. <router-link to="/datasets">Încarcă unul</router-link> mai întâi.
        </p>

        <button class="primary" type="submit" :disabled="submitting || datasets.items.length === 0">
          {{ submitting ? "Se trimite..." : "Pornește simulare" }}
        </button>
      </div>
    </form>
  </div>
</template>
