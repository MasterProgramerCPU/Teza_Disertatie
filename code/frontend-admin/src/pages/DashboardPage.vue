<script setup lang="ts">
import { onMounted } from "vue";
import { useAdminStore } from "@/stores/admin.store";

const admin = useAdminStore();

onMounted(() => admin.fetchStats());

function fmt(n: number): string {
  return n.toLocaleString("ro-RO");
}
</script>

<template>
  <h1>Privire de ansamblu</h1>
  <p class="muted">Statistici globale ale instanței E-Medicine SIR Workbench.</p>

  <p v-if="!admin.stats" class="muted">Se încarcă…</p>

  <div v-else class="grid">
    <div class="metric">
      <div class="value">{{ fmt(admin.stats.users) }}</div>
      <div class="label">Utilizatori înregistrați</div>
      <div class="sub">din care <strong>{{ admin.stats.super_admins }}</strong> super admini</div>
    </div>
    <div class="metric">
      <div class="value">{{ fmt(admin.stats.studies) }}</div>
      <div class="label">Studii active</div>
      <div class="sub muted">grupate per boală</div>
    </div>
    <div class="metric">
      <div class="value">{{ fmt(admin.stats.datasets) }}</div>
      <div class="label">Seturi de date</div>
      <div class="sub">cu <strong>{{ fmt(admin.stats.epi_records) }}</strong> înregistrări zilnice</div>
    </div>
    <div class="metric">
      <div class="value">{{ fmt(admin.stats.simulations) }}</div>
      <div class="label">Simulări lansate</div>
      <div class="sub">finalizate: <strong>{{ fmt(admin.stats.simulations_completed) }}</strong></div>
    </div>
    <div class="metric">
      <div class="value">{{ fmt(admin.stats.benchmarks) }}</div>
      <div class="label">Înregistrări benchmark</div>
      <div class="sub muted">wall-time, CPU, memorie peak</div>
    </div>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.metric {
  background: linear-gradient(180deg, #f8f6ed 0%, #ece9d8 100%);
  border: 1px solid var(--c-border-dark);
  border-radius: 0;
  padding: 20px;
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #808080, var(--shadow-sm);
}
.value {
  font-size: 28px;
  font-weight: 700;
  color: var(--c-primary);
  line-height: 1.1;
  text-shadow: 1px 1px 0 #ffffff;
}
.label {
  margin-top: 4px;
  font-weight: 500;
}
.sub {
  margin-top: 8px;
  font-size: 12px;
  color: var(--c-text-muted);
}
</style>
