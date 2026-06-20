import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";
import type { BenchmarkAggregate, BenchmarkRun, Language, ModelType } from "@/types";
import { useStudiesStore } from "@/stores/studies.store";

function base(): string {
  const studies = useStudiesStore();
  if (!studies.currentStudyId) {
    throw new Error("no study selected");
  }
  return `/studies/${studies.currentStudyId}/benchmarks`;
}

export const useBenchmarksStore = defineStore("benchmarks", () => {
  const items = ref<BenchmarkAggregate[]>([]);
  const runs = ref<BenchmarkRun[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchAll() {
    loading.value = true;
    error.value = null;
    try {
      items.value = (await api.get<BenchmarkAggregate[] | null>(base())) ?? [];
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function fetchRuns(model: ModelType, language: Language) {
    loading.value = true;
    error.value = null;
    runs.value = [];
    try {
      runs.value = (await api.get<BenchmarkRun[] | null>(
        `${base()}/${model}/${language}`,
      )) ?? [];
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  return { items, runs, loading, error, fetchAll, fetchRuns };
});
