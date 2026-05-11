<script setup lang="ts">
import { onMounted } from "vue";
import { useBenchmarksStore } from "@/stores/benchmarks.store";
import BenchmarkTable from "@/components/BenchmarkTable.vue";

const benchmarks = useBenchmarksStore();

onMounted(() => benchmarks.fetchAll());
</script>

<template>
  <h1>Benchmarks</h1>
  <p class="muted">Agregarea metricilor pe simulările finalizate, grupate per limbaj.</p>

  <p v-if="benchmarks.error" class="alert error">{{ benchmarks.error }}</p>

  <div class="card">
    <BenchmarkTable :items="benchmarks.items" />
  </div>
</template>
