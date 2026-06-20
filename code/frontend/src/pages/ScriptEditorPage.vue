<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { VueMonacoEditor } from "@guolao/vue-monaco-editor";
import { useScriptDraftsStore } from "@/stores/script-drafts.store";
import { useDatasetsStore } from "@/stores/datasets.store";
import { useSimulationsStore } from "@/stores/simulations.store";
import { useStudiesStore } from "@/stores/studies.store";
import { useTheme } from "@/composables/useTheme";
import CompartmentChart from "@/components/CompartmentChart.vue";
import type { ScriptDraft, SimulationResultPoint, SimulationRun } from "@/types";

const { theme } = useTheme();
const monacoTheme = computed(() => (theme.value === "dark" ? "vs-dark" : "vs"));

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

const STARTER_PARAMS = `{\n  "alpha": 0.3\n}`;

const drafts = useScriptDraftsStore();
const datasets = useDatasetsStore();
const sims = useSimulationsStore();
const studies = useStudiesStore();

const code = ref(STARTER_SCRIPT);
const parametersText = ref(STARTER_PARAMS);
const datasetId = ref<string>("");
const currentDraftId = ref<string | null>(null);
const draftName = ref("");
const draftDescription = ref("");

// Snapshot al stării "ultima dată salvată", folosit pentru a detecta
// modificări nesalvate (afișează un indicator vizual).
const savedSnapshot = ref({
  code: STARTER_SCRIPT,
  parametersText: STARTER_PARAMS,
  name: "",
  description: "",
});

const run = ref<SimulationRun | null>(null);
const points = ref<SimulationResultPoint[]>([]);
const running = ref(false);
const runError = ref<string | null>(null);
const saveMessage = ref<string | null>(null);

// Backup local per (study, draftId) — supraviețuiește reload-ului chiar dacă
// draft-ul nu a fost încă salvat. Cheia include study_id ca să nu se amestece.
const lsKey = computed(() => {
  const sid = studies.currentStudyId ?? "no-study";
  const did = currentDraftId.value ?? "new";
  return `emedicine.script-editor.${sid}.${did}`;
});

function saveLocalBackup() {
  if (typeof window === "undefined") return;
  const payload = {
    code: code.value,
    parametersText: parametersText.value,
    name: draftName.value,
    description: draftDescription.value,
    datasetId: datasetId.value,
    updatedAt: new Date().toISOString(),
  };
  try {
    localStorage.setItem(lsKey.value, JSON.stringify(payload));
  } catch {
    /* quota exceeded — ignoram */
  }
}

function loadLocalBackup(): boolean {
  if (typeof window === "undefined") return false;
  const raw = localStorage.getItem(lsKey.value);
  if (!raw) return false;
  try {
    const obj = JSON.parse(raw);
    if (typeof obj.code === "string") code.value = obj.code;
    if (typeof obj.parametersText === "string") parametersText.value = obj.parametersText;
    if (typeof obj.name === "string") draftName.value = obj.name;
    if (typeof obj.description === "string") draftDescription.value = obj.description;
    if (typeof obj.datasetId === "string") datasetId.value = obj.datasetId;
    return true;
  } catch {
    return false;
  }
}

function clearLocalBackup() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(lsKey.value);
}

const series = computed(() =>
  points.value.length > 0 ? [{ label: draftName.value || "script", points: points.value }] : [],
);

const isDirty = computed(() => {
  return (
    code.value !== savedSnapshot.value.code ||
    parametersText.value !== savedSnapshot.value.parametersText ||
    draftName.value !== savedSnapshot.value.name ||
    draftDescription.value !== savedSnapshot.value.description
  );
});

onMounted(async () => {
  await Promise.all([datasets.fetchAll(), drafts.fetchAll()]);
  // Backup local pentru "new draft" — dacă există ceva, îl restaurăm chiar și
  // pentru un draft nesalvat încă.
  loadLocalBackup();
  if (!datasetId.value && datasets.items.length > 0) {
    datasetId.value = datasets.items[0].id;
  }
});

// Auto-save în localStorage la fiecare modificare (debounced 500ms).
let saveTimer: ReturnType<typeof setTimeout> | null = null;
watch([code, parametersText, draftName, draftDescription, datasetId], () => {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(saveLocalBackup, 500);
});

watch(saveMessage, (v) => {
  if (v) setTimeout(() => (saveMessage.value = null), 3000);
});

function parseParameters(): Record<string, unknown> {
  const txt = parametersText.value.trim();
  if (!txt) return {};
  const obj = JSON.parse(txt);
  if (typeof obj !== "object" || obj === null) throw new Error("parametrii trebuie sa fie un obiect JSON");
  return obj;
}

async function loadDraft(d: ScriptDraft) {
  if (isDirty.value && !confirm("Ai modificări nesalvate. Vrei să continui și să le pierzi?")) {
    return;
  }
  const full = await drafts.get(d.id);
  currentDraftId.value = full.id;
  draftName.value = full.name;
  draftDescription.value = full.description;
  code.value = full.script_content;
  parametersText.value = JSON.stringify(full.parameters_json ?? {}, null, 2);
  savedSnapshot.value = {
    code: code.value,
    parametersText: parametersText.value,
    name: draftName.value,
    description: draftDescription.value,
  };
  clearLocalBackup();
  saveMessage.value = `Încărcat: ${full.name}`;
}

function newDraft() {
  if (isDirty.value && !confirm("Ai modificări nesalvate. Vrei să continui și să le pierzi?")) {
    return;
  }
  clearLocalBackup();
  currentDraftId.value = null;
  draftName.value = "";
  draftDescription.value = "";
  code.value = STARTER_SCRIPT;
  parametersText.value = STARTER_PARAMS;
  savedSnapshot.value = {
    code: STARTER_SCRIPT,
    parametersText: STARTER_PARAMS,
    name: "",
    description: "",
  };
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
    savedSnapshot.value = {
      code: code.value,
      parametersText: parametersText.value,
      name: draftName.value,
      description: draftDescription.value,
    };
    clearLocalBackup();
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

function fmtRelative(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  const min = Math.floor(diff / 60000);
  if (min < 1) return "acum câteva sec.";
  if (min < 60) return `acum ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `acum ${h}h`;
  return new Date(iso).toLocaleDateString("ro-RO");
}
</script>

<template>
  <div class="editor-page">
    <!-- Sidebar drafts -->
    <aside class="sidebar">
      <header class="sidebar-head">
        <h3>Draft-uri</h3>
        <span class="count">{{ drafts.items.length }}</span>
        <button type="button" @click="newDraft" class="btn-new" title="Draft nou">+ nou</button>
      </header>

      <p v-if="drafts.loading" class="muted">Se încarcă…</p>

      <p v-else-if="drafts.items.length === 0" class="empty">
        Niciun draft salvat în acest studiu.<br/>
        Scrie cod și apasă <strong>Salvează</strong>.
      </p>

      <ul v-else class="draft-list">
        <li
          v-for="d in drafts.items"
          :key="d.id"
          :class="{ active: d.id === currentDraftId }"
        >
          <button class="draft-row" type="button" @click="loadDraft(d)">
            <div class="draft-name">
              <span class="draft-dot" v-if="d.id === currentDraftId && isDirty" title="Modificări nesalvate">●</span>
              {{ d.name }}
            </div>
            <div class="draft-meta">{{ fmtRelative(d.updated_at) }}</div>
          </button>
          <button type="button" class="draft-del" @click="deleteDraft(d)" title="Șterge">✕</button>
        </li>
      </ul>
    </aside>

    <!-- Workspace -->
    <section class="workspace">
      <!-- Bara de sus: nume + descriere + acțiuni -->
      <div class="ws-header">
        <div class="field">
          <label>
            Nume draft
            <span class="dirty" v-if="isDirty" title="Modificări nesalvate">●</span>
          </label>
          <input
            v-model="draftName"
            placeholder="Obligatoriu pentru salvare"
            class="input-name"
          />
        </div>
        <div class="field flex-grow">
          <label>Descriere</label>
          <input
            v-model="draftDescription"
            placeholder="Opțional — la ce folosește scriptul?"
            class="input-desc"
          />
        </div>
        <button type="button" @click="saveDraft" class="btn primary save-btn">
          {{ currentDraftId ? "Actualizează" : "Salvează" }}
        </button>
      </div>

      <!-- Editorul Monaco -->
      <div class="editor-host">
        <VueMonacoEditor
          v-model:value="code"
          language="python"
          :theme="monacoTheme"
          :options="{
            minimap: { enabled: false },
            fontSize: 13,
            tabSize: 4,
            automaticLayout: true,
            scrollBeyondLastLine: false,
            lineNumbers: 'on',
            renderWhitespace: 'selection',
          }"
        />
      </div>

      <!-- Bara de rulare -->
      <div class="run-bar">
        <div class="field">
          <label>Dataset</label>
          <select v-model="datasetId">
            <option v-for="d in datasets.items" :key="d.id" :value="d.id">
              {{ d.name }} ({{ d.record_count }} înreg.)
            </option>
          </select>
        </div>
        <div class="field flex-grow">
          <label>Parametri (JSON)</label>
          <textarea
            v-model="parametersText"
            rows="3"
            spellcheck="false"
            class="params-area"
          ></textarea>
        </div>
        <button
          type="button"
          @click="runScript"
          :disabled="running"
          class="btn run-btn"
        >
          {{ running ? "Se rulează…" : "▶ Rulează" }}
        </button>
      </div>

      <!-- Mesaj de salvare -->
      <transition name="fade">
        <div v-if="saveMessage" class="toast">{{ saveMessage }}</div>
      </transition>

      <!-- Status + rezultate -->
      <div v-if="run || runError" class="results">
        <div v-if="run" class="status-box" :class="run.status">
          <strong>Status:</strong> {{ run.status }}
          <span v-if="run.completed_at"> · finalizat {{ new Date(run.completed_at).toLocaleTimeString("ro-RO") }}</span>
        </div>
        <div v-if="runError" class="error-box">{{ runError }}</div>
        <CompartmentChart v-if="series.length > 0" :series="series" :height="320" />
      </div>
    </section>
  </div>
</template>

<style scoped>
/* Layout pe 2 coloane, fiecare cu înălțime controlată prin grid 1fr. */
.editor-page {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 12px;
  min-height: 70vh;
}

@media (max-width: 760px) {
  .editor-page { grid-template-columns: 1fr; }
}

/* ============ SIDEBAR ============ */
.sidebar {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--c-border-dark);
  background: var(--c-surface);
  box-shadow: inset 1px 1px 0 var(--c-border-light), inset -1px -1px 0 var(--c-border);
  min-height: 0;
}

.sidebar-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  background: linear-gradient(90deg, var(--c-title-end) 0%, var(--c-title-start) 72%, var(--c-title-end-glow) 100%);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  text-shadow: 1px 1px 0 var(--c-primary-deep);
  border-bottom: 1px solid var(--c-border-deep);
}

.sidebar-head h3 { margin: 0; font-size: 12px; color: #fff; }
.count {
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
  padding: 0 6px;
  font-size: 10px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  text-shadow: none;
  font-weight: 600;
}
.btn-new {
  margin-left: auto;
  background: linear-gradient(180deg, var(--btn-bg-1) 0%, var(--btn-bg-2) 48%, var(--btn-bg-3) 100%);
  color: var(--btn-text);
  border: 1px solid var(--btn-border);
  box-shadow: inset 1px 1px 0 var(--btn-inset-light), inset -1px -1px 0 var(--btn-inset-dark);
  padding: 2px 8px;
  font-size: 11px;
  cursor: pointer;
}
.btn-new:hover { background: linear-gradient(180deg, var(--btn-hover-1) 0%, var(--btn-hover-2) 48%, var(--btn-hover-3) 100%); }

.muted { color: var(--c-text-muted); font-size: 12px; padding: 10px; margin: 0; }
.empty {
  padding: 16px 12px;
  color: var(--c-text-muted);
  font-size: 12px;
  text-align: center;
  line-height: 1.5;
}

.draft-list {
  list-style: none;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  flex: 1;
}
.draft-list li {
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid var(--c-border);
  transition: background var(--t-fast) var(--easing);
}
.draft-list li.active { background: var(--table-row-hover); }
.draft-list li:hover:not(.active) { background: var(--c-surface-soft); }

.draft-row {
  flex: 1;
  text-align: left;
  padding: 7px 10px;
  background: transparent;
  color: var(--c-text);
  border: 0;
  cursor: pointer;
  min-width: 0;
}
.draft-name {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  font-size: 12px;
  color: var(--c-text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.draft-dot { color: var(--c-warning); font-size: 14px; }
.draft-meta { color: var(--c-text-muted); font-size: 11px; margin-top: 2px; }

.draft-del {
  background: transparent;
  border: 0;
  color: var(--c-text-muted);
  cursor: pointer;
  padding: 0 8px;
  font-size: 12px;
  transition: color var(--t-fast) var(--easing);
}
.draft-del:hover { color: var(--c-danger); }

/* ============ WORKSPACE ============ */
.workspace {
  display: grid;
  grid-template-rows: auto 1fr auto auto;
  gap: 10px;
  min-width: 0;
  min-height: 0;
}

.ws-header {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(220px, 2fr) auto;
  gap: 10px;
  align-items: end;
  padding: 10px;
  background: var(--c-surface);
  border: 1px solid var(--c-border-dark);
  box-shadow: inset 1px 1px 0 var(--c-border-light), inset -1px -1px 0 var(--c-border);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.field.flex-grow { flex: 1; }
.field label {
  font-size: 11px;
  font-weight: 700;
  color: var(--c-text);
  display: flex;
  align-items: center;
  gap: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.dirty { color: var(--c-warning); font-size: 14px; }
.field input,
.field select,
.field textarea {
  width: 100%;
  font-size: 12px;
  padding: 4px 6px;
  border: 1px solid var(--input-border);
  background: var(--input-bg);
  color: var(--input-text);
  font-family: inherit;
}
.params-area {
  font-family: var(--font-mono);
  resize: vertical;
}

.save-btn,
.run-btn {
  min-height: 30px;
  padding: 4px 16px;
  font-size: 12px;
  font-weight: 700;
  border-radius: 0;
  white-space: nowrap;
  align-self: end;
}
.run-btn {
  background: linear-gradient(180deg, #4ade80 0%, #22a045 50%, #15821f 100%);
  color: #fff;
  border: 1px solid #0d5212;
  box-shadow: inset 1px 1px 0 #a3f0bb, inset -1px -1px 0 #0d5212;
}
.run-btn:hover:not(:disabled) {
  background: linear-gradient(180deg, #5fe790 0%, #2cb350 50%, #1a9027 100%);
}
.run-btn:disabled {
  background: linear-gradient(180deg, #c0c0c0 0%, #909090 100%);
  color: var(--c-text-muted);
  border-color: #606060;
  cursor: not-allowed;
}

/* Editor — ocupă restul spațiului. min-height:0 e cheia ca grid 1fr să nu
   crească dincolo de container. */
.editor-host {
  min-height: 360px;
  border: 1px solid var(--c-border-dark);
  background: var(--input-bg);
  box-shadow: inset 1px 1px 0 var(--c-border-dark), inset -1px -1px 0 var(--c-border-light);
  overflow: hidden;
  position: relative;
}

.run-bar {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(240px, 2fr) auto;
  gap: 10px;
  align-items: end;
  padding: 10px;
  background: var(--c-surface);
  border: 1px solid var(--c-border-dark);
  box-shadow: inset 1px 1px 0 var(--c-border-light), inset -1px -1px 0 var(--c-border);
}

.toast {
  position: fixed;
  right: 24px;
  bottom: 50px;
  background: linear-gradient(180deg, #4ade80 0%, #15821f 100%);
  color: #fff;
  padding: 8px 16px;
  border: 1px solid #0d5212;
  box-shadow: var(--shadow-md);
  font-weight: 700;
  font-size: 13px;
  z-index: 10;
}

/* Rezultate */
.results {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  background: var(--c-surface);
  border: 1px solid var(--c-border-dark);
  box-shadow: inset 1px 1px 0 var(--c-border-light), inset -1px -1px 0 var(--c-border);
}

.status-box {
  padding: 6px 10px;
  background: var(--c-surface-soft);
  color: var(--c-text);
  border: 1px solid var(--c-border);
  font-size: 12px;
}
.status-box.completed {
  background: rgba(74, 222, 128, 0.18);
  border-color: #4ade80;
  color: #1f5f1f;
}
[data-theme="dark"] .status-box.completed { color: #c8f0d4; }
.status-box.failed { background: rgba(176, 0, 0, 0.18); border-color: #b00000; color: #800000; }
[data-theme="dark"] .status-box.failed { color: #fecaca; }
.error-box {
  background: rgba(176, 0, 0, 0.18);
  color: #800000;
  border: 1px solid #b00000;
  padding: 6px 10px;
  font-size: 12px;
}
[data-theme="dark"] .error-box { color: #fecaca; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s, transform 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(10px); }

@media (max-width: 760px) {
  .ws-header, .run-bar { grid-template-columns: 1fr; }
  .save-btn, .run-btn { width: 100%; }
}
</style>
