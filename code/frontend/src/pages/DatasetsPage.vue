<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useDatasetsStore } from "@/stores/datasets.store";
import DatasetUpload from "@/components/DatasetUpload.vue";

const datasets = useDatasetsStore();
const showUpload = ref(false);

onMounted(() => datasets.fetchAll());

async function remove(id: string) {
  if (!confirm("Ștergi acest set de date și toate simulările asociate?")) return;
  await datasets.remove(id);
}
</script>

<template>
  <div class="row" style="justify-content: space-between; margin-bottom: 16px;">
    <h1 style="margin-bottom: 0;">Seturi de date</h1>
    <button class="primary" @click="showUpload = !showUpload">
      {{ showUpload ? "Anulează" : "Încarcă CSV" }}
    </button>
  </div>

  <div v-if="showUpload" class="card">
    <DatasetUpload @uploaded="showUpload = false" />
  </div>

  <p v-if="datasets.error" class="alert error">{{ datasets.error }}</p>

  <div class="card">
    <table v-if="datasets.items.length > 0">
      <thead>
        <tr><th>Nume</th><th>Cod boală</th><th>Înregistrări</th><th>Încărcat</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="d in datasets.items" :key="d.id">
          <td><router-link :to="`/datasets/${d.id}`">{{ d.name }}</router-link></td>
          <td>{{ d.disease_code }}</td>
          <td>{{ d.record_count.toLocaleString() }}</td>
          <td>{{ new Date(d.uploaded_at).toLocaleString() }}</td>
          <td><button class="danger" @click="remove(d.id)">Șterge</button></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">Niciun set de date încă. Folosește butonul „Încarcă CSV" pentru a adăuga unul.</p>
  </div>
</template>
