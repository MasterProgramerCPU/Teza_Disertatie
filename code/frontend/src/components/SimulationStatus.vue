<script setup lang="ts">
import type { SimulationStatus } from "@/types";

defineProps<{ status: SimulationStatus }>();

const labels: Record<SimulationStatus, string> = {
  pending: "În așteptare",
  running: "Se execută",
  completed: "Finalizat",
  failed: "Eșuat",
};
</script>

<template>
  <span class="badge" :class="status">{{ labels[status] }}</span>
</template>
