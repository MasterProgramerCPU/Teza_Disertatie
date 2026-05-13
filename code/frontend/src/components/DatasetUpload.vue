<script setup lang="ts">
import { ref } from "vue";
import { useDatasetsStore } from "@/stores/datasets.store";

const emit = defineEmits<{ uploaded: [] }>();
const datasets = useDatasetsStore();

const name = ref("");
const diseaseCode = ref("COVID-19");
const file = ref<File | null>(null);
const dragOver = ref(false);
const submitting = ref(false);
const error = ref<string | null>(null);

function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files && input.files.length > 0) {
    file.value = input.files[0];
    if (!name.value) name.value = file.value.name.replace(/\.csv$/i, "");
  }
}

function onDrop(e: DragEvent) {
  e.preventDefault();
  dragOver.value = false;
  if (e.dataTransfer?.files?.[0]) {
    file.value = e.dataTransfer.files[0];
    if (!name.value) name.value = file.value.name.replace(/\.csv$/i, "");
  }
}

async function submit() {
  if (!file.value || !name.value || !diseaseCode.value) {
    error.value = "completează toate câmpurile";
    return;
  }
  error.value = null;
  submitting.value = true;
  try {
    await datasets.upload(name.value, diseaseCode.value, file.value);
    name.value = "";
    file.value = null;
    emit("uploaded");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="upload">
    <div class="row" style="margin-bottom: 12px;">
      <div class="flex-1">
        <label>Nume</label>
        <input v-model="name" placeholder="ex. COVID-19 România" :disabled="submitting" />
      </div>
      <div class="flex-1">
        <label>Cod boală</label>
        <input v-model="diseaseCode" :disabled="submitting" />
      </div>
    </div>

    <label>Fișier CSV</label>
    <div
      class="dropzone"
      :class="{ over: dragOver, has: !!file }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop="onDrop"
    >
      <input type="file" accept=".csv" @change="onFile" :disabled="submitting" />
      <p v-if="file">{{ file.name }} ({{ (file.size / 1024).toFixed(1) }} KB)</p>
      <p v-else class="muted">Drag & drop sau click pentru CSV</p>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <button class="primary" @click="submit" :disabled="submitting || !file" style="margin-top: 12px;">
      {{ submitting ? "Se încarcă..." : "Încarcă" }}
    </button>
  </div>
</template>

<style scoped>
.dropzone {
  border: 1px inset #808080;
  border-radius: 0;
  padding: 24px;
  text-align: center;
  transition: border-color 0.15s, background 0.15s;
  position: relative;
  background:
    repeating-linear-gradient(45deg, rgba(255, 255, 255, 0.6) 0 6px, rgba(236, 233, 216, 0.8) 6px 12px),
    var(--c-surface-soft);
}
.dropzone.over {
  border-color: var(--c-primary);
  background: #dbeafe;
}
.dropzone.has {
  border-color: var(--c-success);
  border-style: solid;
  background: #e1f5d6;
}
.dropzone input[type="file"] {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
</style>
