<script setup lang="ts">
import { reactive, watch } from "vue";
import type { Language } from "@/types";

interface Model {
  beta: number;
  gamma: number;
  t_max: number;
  language: Language;
}

const props = defineProps<{
  modelValue: Model;
  disabled?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [Model] }>();

const local = reactive<Model>({ ...props.modelValue });

watch(local, (v) => emit("update:modelValue", { ...v }), { deep: true });
watch(() => props.modelValue, (v) => Object.assign(local, v));

const r0 = () => (local.gamma > 0 ? (local.beta / local.gamma).toFixed(2) : "—");
</script>

<template>
  <div class="col">
    <div class="row">
      <div class="flex-1">
        <label>Limbaj</label>
        <select v-model="local.language" :disabled="disabled">
          <option value="python">Python</option>
          <option value="r">R</option>
          <option value="julia">Julia</option>
        </select>
      </div>
      <div class="flex-1">
        <label>t_max (zile)</label>
        <input v-model.number="local.t_max" type="number" min="1" :disabled="disabled" />
      </div>
    </div>
    <div class="row">
      <div class="flex-1">
        <label>beta (rata de transmitere)</label>
        <input v-model.number="local.beta" type="number" step="0.001" min="0" :disabled="disabled" />
      </div>
      <div class="flex-1">
        <label>gamma (rata de recuperare)</label>
        <input v-model.number="local.gamma" type="number" step="0.001" min="0" :disabled="disabled" />
      </div>
    </div>
    <div class="muted">R<sub>0</sub> = beta / gamma = <strong>{{ r0() }}</strong></div>
  </div>
</template>
