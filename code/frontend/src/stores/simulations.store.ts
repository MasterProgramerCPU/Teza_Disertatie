import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";
import type {
  CreateSimulationPayload,
  SimulationResultPoint,
  SimulationRun,
} from "@/types";

const TERMINAL = new Set(["completed", "failed"]);

export const useSimulationsStore = defineStore("simulations", () => {
  const items = ref<SimulationRun[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchAll() {
    loading.value = true;
    error.value = null;
    try {
      items.value = await api.get<SimulationRun[]>("/simulations");
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function get(id: string): Promise<SimulationRun> {
    return api.get<SimulationRun>(`/simulations/${id}`);
  }

  async function results(id: string): Promise<SimulationResultPoint[]> {
    return api.get<SimulationResultPoint[]>(`/simulations/${id}/results`);
  }

  async function create(payload: CreateSimulationPayload): Promise<SimulationRun> {
    const run = await api.post<SimulationRun>("/simulations", payload);
    items.value = [run, ...items.value];
    return run;
  }

  /** Poll until the simulation reaches a terminal status. */
  async function pollUntilDone(
    id: string,
    onUpdate: (run: SimulationRun) => void,
    intervalMs = 2000,
    timeoutMs = 5 * 60_000,
  ): Promise<SimulationRun> {
    const start = Date.now();
    while (true) {
      const run = await get(id);
      onUpdate(run);
      if (TERMINAL.has(run.status)) return run;
      if (Date.now() - start > timeoutMs) {
        throw new Error("simulation polling timed out");
      }
      await new Promise((res) => setTimeout(res, intervalMs));
    }
  }

  async function exportCSV(id: string): Promise<Blob> {
    return api.getBlob(`/simulations/${id}/export`);
  }

  return { items, loading, error, fetchAll, get, results, create, pollUntilDone, exportCSV };
});
