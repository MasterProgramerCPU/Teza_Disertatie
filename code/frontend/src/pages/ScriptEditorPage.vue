<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { VueMonacoEditor } from "@guolao/vue-monaco-editor";
import { useScriptDraftsStore } from "@/stores/script-drafts.store";
import { useDatasetsStore } from "@/stores/datasets.store";
import { useSimulationsStore } from "@/stores/simulations.store";
import CompartmentChart from "@/components/CompartmentChart.vue";
import type { ScriptDraft, SimulationResultPoint, SimulationRun } from "@/types";

const STARTER_SCRIPT = `# Editorul executa scriptul Python pe dataset-ul ales.
# Functia main() trebuie sa intoarca [{"t": int, "compartments": {nume: float}}, ...].
# Bibliotecile preinstalate: numpy, scipy, pandas, scikit-learn.

def main(records, parameters, context):
    alpha = parameters.get("alpha", 0.3)
    series = [r["infected"] for r in records]
    if not series:
        return []
    smooth = [float(series[0])]
    for x in series[1:]:
        smooth.append(alpha * x + (1 - alpha) * smooth[-1])
    return [
        {"t": i, "compartments": {"observed": float(v), "smooth": float(s)}}
        for i, (v, s) in enumerate(zip(series, smooth))
    ]
`;

const drafts = useScriptDraftsStore();
const datasets = useDatasetsStore();
const sims = useSimulationsStore();

const code = ref(STARTER_SCRIPT);
const parametersText = ref(`{\n  "alpha": 0.3\n}`);
const datasetId = ref<string>("");
const currentDraftId = ref<string | null>(null);
const draftName = ref("");
const draftDescription = ref("");

const run = ref<SimulationRun | null>(null);
const points = ref<SimulationResultPoint[]>([]);
const running = ref(false);
const runError = ref<string | null>(null);
const saveMessage = ref<string | null>(null);

const series = computed(() =>
  points.value.length > 0 ? [{ label: draftName.value || "script", points: points.value }] : [],
);

onMounted(async () => {
  await Promise.all([datasets.fetchAll(), drafts.fetchAll()]);
  if (!datasetId.value && datasets.items.length > 0) {
    datasetId.value = datasets.items[0].id;
  }
});

watch(saveMessage, (v) => {
  if (v) setTimeout(() => (saveMessage.value = null), 3000);
});

function parseParameters(): Record<string, number> {
  const txt = parametersText.value.trim();
  if (!txt) return {};
  const obj = JSON.parse(txt);
  if (typeof obj !== "object" || obj === null) throw new Error("parametrii trebuie sa fie un obiect JSON");
  return obj;
}

async function loadDraft(d: ScriptDraft) {
  // Lista nu contine script_content; il aducem explicit.
  const full = await drafts.get(d.id);
  currentDraftId.value = full.id;
  draftName.value = full.name;
  draftDescription.value = full.description;
  code.value = full.script_content;
  parametersText.value = JSON.stringify(full.parameters_json ?? {}, null, 2);
  saveMessage.value = `Incarcat: ${full.name}`;
}

function newDraft() {
  currentDraftId.value = null;
  draftName.value = "";
  draftDescription.value = "";
  code.value = STARTER_SCRIPT;
  parametersText.value = `{\n  "alpha": 0.3\n}`;
}

async function saveDraft() {
  runError.value = null;
  let parameters: Record<string, unknown>;
  try {
    parameters = parseParameters();
  } catch (e) {
    runError.value = `JSON parametri invalid: ${(e as Error).message}`;
    return;
  }
  const name = draftName.value.trim();
  if (!name) {
    runError.value = "Numele draft-ului este obligatoriu pentru salvare.";
    return;
  }
  try {
    if (currentDraftId.value) {
      await drafts.update(currentDraftId.value, {
        name,
        description: draftDescription.value,
        script_content: code.value,
        parameters_json: parameters,
      });
      saveMessage.value = `Actualizat: ${name}`;
    } else {
      const d = await drafts.create({
        name,
        description: draftDescription.value,
        script_content: code.value,
        parameters_json: parameters,
      });
      currentDraftId.value = d.id;
      saveMessage.value = `Salvat: ${name}`;
    }
  } catch (e) {
    runError.value = (e as Error).message;
  }
}

async function deleteDraft(d: ScriptDraft) {
  if (!confirm(`Stergi draft-ul "${d.name}"?`)) return;
  await drafts.remove(d.id);
  if (currentDraftId.value === d.id) newDraft();
}

async function runScript() {
  runError.value = null;
  points.value = [];
  run.value = null;
  if (!datasetId.value) {
    runError.value = "Alege un dataset.";
    return;
  }
  let parameters: Record<string, number>;
  try {
    const raw = parseParameters();
    parameters = Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, Number(v)]));
  } catch (e) {
    runError.value = `JSON parametri invalid: ${(e as Error).message}`;
    return;
  }
  running.value = true;
  try {
    const created = await sims.create({
      dataset_id: datasetId.value,
      model_type: "script",
      parameters,
      t_max: 0,
      script_content: code.value,
    });
    run.value = created;
    const finalRun = await sims.pollUntilDone(created.id, (r) => (run.value = r));
    if (finalRun.status === "completed") {
      points.value = await sims.results(created.id);
    } else {
      runError.value = finalRun.error_message || "Simularea a esuat.";
    }
  } catch (e) {
    runError.value = (e as Error).message;
  } finally {
    running.value = false;
  }
}
</script>

<template>
  <div class="editor-page">
    <aside class="sidebar">
      <div class="sidebar-header">
        <h3>Draft-uri</h3>
        <button @click="newDraft" class="btn-small" title="Draft nou">+ nou</button>
      </div>
      <div v-if="drafts.loading" class="muted">se incarca...</div>
      <div v-else-if="drafts.items.length === 0" class="muted">
        Niciun draft salvat. Scrie cod si apasa "Salveaza" pentru a-l pastra.
      </div>
      <ul v-else class="draft-list">
        <li v-for="d in drafts.items" :key="d.id"
            :class="{ active: d.id === currentDraftId }">
          <button class="draft-row" @click="loadDraft(d)">
            <div class="draft-name">{{ d.name }}</div>
            <div class="draft-meta">{{ new Date(d.updated_at).toLocaleString() }}</div>
          </button>
          <button class="draft-del" @click="deleteDraft(d)" title="Sterge">×</button>
        </li>
      </ul>
    </aside>

    <main class="workspace">
      <header class="workspace-header">
        <input v-model="draftName" placeholder="Nume draft (obligatoriu pentru salvare)"
               class="input-name" />
        <input v-model="draftDescription" placeholder="Descriere (optional)"
               class="input-desc" />
        <button @click="saveDraft" class="btn btn-save">Salveaza</button>
      </header>

      <div class="editor-host">
        <VueMonacoEditor
          v-model:value="code"
          language="python"
          theme="vs"
          :options="{ minimap: { enabled: false }, fontSize: 13, tabSize: 4, automaticLayout: true, scrollBeyondLastLine: false }"
        />
      </div>

      <section class="run-bar">
        <label class="field">
          <span>Dataset</span>
          <select v-model="datasetId">
            <option v-for="d in datasets.items" :key="d.id" :value="d.id">
              {{ d.name }} ({{ d.record_count }} inreg.)
            </option>
          </select>
        </label>
        <label class="field params">
          <span>Parametri (JSON)</span>
          <textarea v-model="parametersText" rows="3" spellcheck="false"></textarea>
        </label>
        <button @click="runScript" :disabled="running" class="btn btn-run">
          {{ running ? "Se ruleaza..." : "▶ Ruleaza" }}
        </button>
      </section>

      <transition name="fade">
        <div v-if="saveMessage" class="toast">{{ saveMessage }}</div>
      </transition>

      <section v-if="run || runError" class="results">
        <div v-if="run" class="status-box" :class="run.status">
          <strong>Status:</strong> {{ run.status }}
          <span v-if="run.completed_at"> · finalizat {{ new Date(run.completed_at).toLocaleTimeString() }}</span>
        </div>
        <div v-if="runError" class="error-box">{{ runError }}</div>
        <CompartmentChart v-if="series.length > 0" :series="series" :height="320" />
      </section>
    </main>
  </div>
</template>

<style scoped>
.editor-page { display: grid; grid-template-columns: 260px 1fr; gap: 1rem; padding: 1rem; height: calc(100vh - 64px); }
.sidebar { border: 1px solid #ddd; border-radius: 6px; padding: 0.75rem; overflow-y: auto; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.sidebar h3 { margin: 0; font-size: 0.95rem; }
.btn-small { padding: 0.25rem 0.5rem; font-size: 0.85rem; }
.muted { color: #888; font-size: 0.85rem; }
.draft-list { list-style: none; padding: 0; margin: 0; }
.draft-list li { display: flex; align-items: stretch; border-bottom: 1px solid #eee; }
.draft-list li.active { background: #f0f7ff; }
.draft-row { flex: 1; text-align: left; padding: 0.5rem; background: transparent; border: 0; cursor: pointer; }
.draft-row:hover { background: #f5f5f5; }
.draft-name { font-weight: 600; font-size: 0.9rem; }
.draft-meta { color: #888; font-size: 0.75rem; }
.draft-del { background: transparent; border: 0; color: #c33; cursor: pointer; padding: 0 0.5rem; font-size: 1.2rem; }
.workspace { display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; }
.workspace-header { display: flex; gap: 0.5rem; align-items: center; }
.input-name { flex: 1; padding: 0.4rem; }
.input-desc { flex: 2; padding: 0.4rem; }
.btn { padding: 0.5rem 1rem; cursor: pointer; }
.btn-save { background: #2876d2; color: white; border: 0; border-radius: 4px; }
.btn-run { background: #1f9a4a; color: white; border: 0; border-radius: 4px; }
.btn-run:disabled { opacity: 0.6; cursor: not-allowed; }
.editor-host { flex: 1; min-height: 300px; border: 1px solid #ddd; border-radius: 4px; overflow: hidden; }
.run-bar { display: flex; gap: 0.75rem; align-items: flex-end; }
.field { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.85rem; }
.field.params { flex: 1; }
.field textarea, .field select { font-family: ui-monospace, "SFMono-Regular", Menlo, monospace; padding: 0.3rem; }
.toast { background: #1f9a4a; color: white; padding: 0.5rem 1rem; border-radius: 4px; }
.results { padding-top: 0.5rem; border-top: 1px solid #eee; }
.status-box { padding: 0.5rem; border-radius: 4px; background: #f0f0f0; margin-bottom: 0.5rem; }
.status-box.completed { background: #e0f5e8; }
.status-box.failed, .error-box { background: #ffe8e8; color: #a00; padding: 0.5rem; border-radius: 4px; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
