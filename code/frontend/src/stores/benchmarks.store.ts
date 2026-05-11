import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";
import type { BenchmarkAggregate } from "@/types";

export const useBenchmarksStore = defineStore("benchmarks", () => {
  const items = ref<BenchmarkAggregate[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchAll() {
    loading.value = true;
    error.value = null;
    try {
      items.value = await api.get<BenchmarkAggregate[]>("/benchmarks");
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  return { items, loading, error, fetchAll };
});
