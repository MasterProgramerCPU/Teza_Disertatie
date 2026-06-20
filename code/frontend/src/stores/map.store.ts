import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";
import type { MapResponse } from "@/types";
import { useStudiesStore } from "@/stores/studies.store";

export const useMapStore = defineStore("map", () => {
  const data = ref<MapResponse | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetch(model: string, language: string) {
    const studies = useStudiesStore();
    if (!studies.currentStudyId) throw new Error("no study selected");
    loading.value = true;
    error.value = null;
    try {
      const q = new URLSearchParams({ model, language });
      data.value = await api.get<MapResponse>(
        `/studies/${studies.currentStudyId}/map?${q.toString()}`,
      );
    } catch (e) {
      error.value = (e as Error).message;
      data.value = null;
    } finally {
      loading.value = false;
    }
  }

  return { data, loading, error, fetch };
});
