<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import { defaultParameters, MODEL_LABELS, MODEL_PARAMETER_ORDER, PARAMETER_LABELS } from "@/model-presets";
import type { Language, ModelType } from "@/types";

interface Model {
  model_type: ModelType;
  parameters: Record<string, number>;
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

watch(() => local.model_type, (modelType) => {
  local.parameters = defaultParameters(modelType);
});

const parameterKeys = computed(() => MODEL_PARAMETER_ORDER[local.model_type]);
const r0 = computed(() => {
  if (local.model_type !== "sir") return null;
  const beta = local.parameters.beta;
  const gamma = local.parameters.gamma;
  return gamma > 0 ? (beta / gamma).toFixed(2) : "—";
});
</script>

<template>
  <div class="col">
    <div class="row">
      <div class="flex-1">
        <label>Model</label>
        <select v-model="local.model_type" :disabled="disabled">
          <option value="sidarth">{{ MODEL_LABELS.sidarth }}</option>
          <option value="sir">{{ MODEL_LABELS.sir }}</option>
        </select>
      </div>
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

    <div class="parameter-grid">
      <div v-for="key in parameterKeys" :key="key">
        <label>{{ PARAMETER_LABELS[key] ?? key }}</label>
        <input
          v-model.number="local.parameters[key]"
          type="number"
          step="0.001"
          min="0"
          :disabled="disabled"
        />
      </div>
    </div>
    <div v-if="r0" class="muted">R<sub>0</sub> = beta / gamma = <strong>{{ r0 }}</strong></div>
  </div>
</template>

<style scoped>
.parameter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}
</style>
