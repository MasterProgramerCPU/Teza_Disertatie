<script setup lang="ts">
import { onMounted, computed } from "vue";
import { useAdminStore } from "@/stores/admin.store";
import type { LabeledCount } from "@/types";

const admin = useAdminStore();

onMounted(async () => {
  await Promise.all([admin.fetchStats(), admin.fetchBreakdown()]);
});

function fmt(n: number): string {
  return n.toLocaleString("ro-RO");
}

const bd = computed(() => admin.breakdown);
const maxTopRecords = computed(
  () => Math.max(1, ...(bd.value?.top_studies_by_records ?? []).map((s) => s.record_count)),
);

function maxOf(items: LabeledCount[]): number {
  return Math.max(1, ...items.map((i) => i.count));
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

  <template v-if="bd">
    <div class="row">
      <div class="card mini">
        <h2>Simulări pe status</h2>
        <ul class="bars">
          <li v-for="b in bd.simulations_by_status" :key="b.label">
            <span class="lbl"><span :class="['badge', `status-${b.label}`]">{{ b.label }}</span></span>
            <span class="bar"><span class="fill" :style="{ width: (b.count / maxOf(bd.simulations_by_status) * 100) + '%' }"></span></span>
            <span class="cnt">{{ fmt(b.count) }}</span>
          </li>
        </ul>
        <p v-if="bd.simulations_by_status.length === 0" class="muted">Nicio simulare.</p>
      </div>

      <div class="card mini">
        <h2>Simulări pe model</h2>
        <ul class="bars">
          <li v-for="b in bd.simulations_by_model" :key="b.label">
            <span class="lbl"><code>{{ b.label }}</code></span>
            <span class="bar"><span class="fill" :style="{ width: (b.count / maxOf(bd.simulations_by_model) * 100) + '%' }"></span></span>
            <span class="cnt">{{ fmt(b.count) }}</span>
          </li>
        </ul>
        <p v-if="bd.simulations_by_model.length === 0" class="muted">Nicio simulare.</p>
      </div>

      <div class="card mini">
        <h2>Simulări pe limbaj</h2>
        <ul class="bars">
          <li v-for="b in bd.simulations_by_language" :key="b.label">
            <span class="lbl"><code>{{ b.label }}</code></span>
            <span class="bar"><span class="fill" :style="{ width: (b.count / maxOf(bd.simulations_by_language) * 100) + '%' }"></span></span>
            <span class="cnt">{{ fmt(b.count) }}</span>
          </li>
        </ul>
        <p v-if="bd.simulations_by_language.length === 0" class="muted">Nicio simulare.</p>
      </div>
    </div>

    <div class="row">
      <div class="card mini">
        <h2>Studii pe boală</h2>
        <ul class="bars">
          <li v-for="b in bd.studies_by_disease" :key="b.label">
            <span class="lbl"><code>{{ b.label }}</code></span>
            <span class="bar"><span class="fill" :style="{ width: (b.count / maxOf(bd.studies_by_disease) * 100) + '%' }"></span></span>
            <span class="cnt">{{ fmt(b.count) }}</span>
          </li>
        </ul>
      </div>

      <div class="card mini">
        <h2>Seturi de date pe boală</h2>
        <ul class="bars">
          <li v-for="b in bd.datasets_by_disease" :key="b.label">
            <span class="lbl"><code>{{ b.label }}</code></span>
            <span class="bar"><span class="fill" :style="{ width: (b.count / maxOf(bd.datasets_by_disease) * 100) + '%' }"></span></span>
            <span class="cnt">{{ fmt(b.count) }}</span>
          </li>
        </ul>
      </div>
    </div>

    <div class="card">
      <h2>Top 10 studii după volumul de înregistrări</h2>
      <ul class="bars top">
        <li v-for="s in bd.top_studies_by_records" :key="s.study_id">
          <span class="lbl">
            <router-link :to="`/studies/${s.study_id}`">{{ s.name }}</router-link>
          </span>
          <span class="bar"><span class="fill" :style="{ width: (s.record_count / maxTopRecords * 100) + '%' }"></span></span>
          <span class="cnt">{{ fmt(s.record_count) }}</span>
        </li>
      </ul>
      <p v-if="bd.top_studies_by_records.length === 0" class="muted">Niciun studiu cu seturi de date.</p>
    </div>
  </template>
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
.label { margin-top: 4px; font-weight: 500; }
.sub   { margin-top: 8px; font-size: 12px; color: var(--c-text-muted); }

.row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
  margin-top: 16px;
}
.card.mini { padding: 12px; }

.bars {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
}
.bars li {
  display: grid;
  grid-template-columns: 90px 1fr 60px;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
}
.bars.top li {
  grid-template-columns: 1fr 2fr 80px;
}
.lbl { font-size: 12px; }
.bar {
  height: 14px;
  background: #ffffff;
  border: 1px solid #808080;
  box-shadow: inset 1px 1px 0 #404040;
  position: relative;
}
.fill {
  display: block;
  height: 100%;
  background: linear-gradient(180deg, #6fb6ff 0%, #2b72f2 60%, #07307f 100%);
  box-shadow: inset 1px 1px 0 #c3dfff, inset -1px -1px 0 #001b5d;
}
.cnt {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  font-weight: 700;
}
.badge {
  display: inline-block;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
  border: 1px solid #404040;
  text-transform: uppercase;
}
.status-completed { background: #c6e7c6; color: #1f5f1f; border-color: #1f5f1f; }
.status-running   { background: #fff2a8; color: #6a5a00; border-color: #6a5a00; }
.status-pending   { background: #d0d0d0; color: #303030; border-color: #404040; }
.status-failed    { background: #f5c6c6; color: #7a0000; border-color: #7a0000; }
</style>
