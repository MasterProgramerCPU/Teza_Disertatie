import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";
import type { ScriptDraft, ScriptDraftPayload } from "@/types";
import { useStudiesStore } from "@/stores/studies.store";

function basePath(): string {
  const studies = useStudiesStore();
  if (!studies.currentStudyId) {
    throw new Error("no study selected");
  }
  return `/studies/${studies.currentStudyId}/script-drafts`;
}

/**
 * Pinia store pentru draft-urile de cod ale cercetatorului.
 * Lista returneaza metadate (fara script_content); get(id) returneaza inclusiv
 * continutul. Toate operatiile sunt filtrate server-side pe user_id.
 */
export const useScriptDraftsStore = defineStore("script-drafts", () => {
  const items = ref<ScriptDraft[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchAll() {
    loading.value = true;
    error.value = null;
    try {
      items.value = (await api.get<ScriptDraft[] | null>(basePath())) ?? [];
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function get(id: string): Promise<ScriptDraft> {
    return api.get<ScriptDraft>(`${basePath()}/${id}`);
  }

  async function create(payload: ScriptDraftPayload): Promise<ScriptDraft> {
    const d = await api.post<ScriptDraft>(basePath(), payload);
    items.value = [d, ...items.value];
    return d;
  }

  async function update(id: string, payload: ScriptDraftPayload): Promise<ScriptDraft> {
    const d = await api.patch<ScriptDraft>(`${basePath()}/${id}`, payload);
    const idx = items.value.findIndex((x) => x.id === id);
    if (idx >= 0) items.value[idx] = { ...d, script_content: "" };
    return d;
  }

  async function remove(id: string): Promise<void> {
    await api.delete(`${basePath()}/${id}`);
    items.value = items.value.filter((x) => x.id !== id);
  }

  function reset() {
    items.value = [];
    error.value = null;
  }

  return { items, loading, error, fetchAll, get, create, update, remove, reset };
});
