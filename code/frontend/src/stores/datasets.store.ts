import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";
import type { Dataset } from "@/types";
import { useStudiesStore } from "@/stores/studies.store";

function basePath(): string {
  const studies = useStudiesStore();
  if (!studies.currentStudyId) {
    throw new Error("no study selected");
  }
  return `/studies/${studies.currentStudyId}/datasets`;
}

export const useDatasetsStore = defineStore("datasets", () => {
  const items = ref<Dataset[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchAll() {
    loading.value = true;
    error.value = null;
    try {
      items.value = (await api.get<Dataset[] | null>(basePath())) ?? [];
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function get(id: string): Promise<Dataset> {
    return api.get<Dataset>(`${basePath()}/${id}`);
  }

  async function upload(name: string, diseaseCode: string, file: File) {
    const form = new FormData();
    form.append("name", name);
    form.append("disease_code", diseaseCode);
    form.append("file", file);
    const created = await api.postForm<Dataset>(basePath(), form);
    items.value = [created, ...items.value];
    return created;
  }

  async function remove(id: string) {
    await api.delete<unknown>(`${basePath()}/${id}`);
    items.value = items.value.filter((d) => d.id !== id);
  }

  return { items, loading, error, fetchAll, get, upload, remove };
});
