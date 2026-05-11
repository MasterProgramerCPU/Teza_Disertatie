<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useDatasetsStore } from "@/stores/datasets.store";
import type { Dataset } from "@/types";

const props = defineProps<{ id: string }>();
const router = useRouter();
const datasets = useDatasetsStore();

const dataset = ref<Dataset | null>(null);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    dataset.value = await datasets.get(props.id);
  } catch (e) {
    error.value = (e as Error).message;
  }
});
</script>

<template>
  <p v-if="error" class="alert error">{{ error }}</p>
  <div v-if="dataset" class="card">
    <div class="row" style="justify-content: space-between; margin-bottom: 16px;">
      <h1 style="margin-bottom: 0;">{{ dataset.name }}</h1>
      <button class="primary" @click="router.push({ name: 'simulation-new', query: { dataset_id: dataset.id }})">
        Pornește simulare
      </button>
    </div>
    <dl class="meta">
      <dt>ID</dt><dd><code>{{ dataset.id }}</code></dd>
      <dt>Cod boală</dt><dd>{{ dataset.disease_code }}</dd>
      <dt>Număr înregistrări</dt><dd>{{ dataset.record_count.toLocaleString() }}</dd>
      <dt>Încărcat la</dt><dd>{{ new Date(dataset.uploaded_at).toLocaleString() }}</dd>
    </dl>
  </div>
</template>

<style scoped>
.meta { display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; }
.meta dt { font-weight: 500; color: var(--c-text-muted); }
.meta dd { margin: 0; }
</style>
