<script setup lang="ts">
import { MODEL_LABELS } from "@/model-presets";
import type { BenchmarkAggregate } from "@/types";

defineProps<{ items: BenchmarkAggregate[] }>();

function fmtMs(v: number): string {
  if (v >= 1000) return (v / 1000).toFixed(2) + " s";
  return v.toFixed(0) + " ms";
}
function fmtMB(v: number): string {
  return v.toFixed(1) + " MB";
}
</script>

<template>
  <table>
    <thead>
      <tr>
        <th>Model</th>
        <th>Limbaj</th>
        <th>Rulări</th>
        <th>Mediana wall</th>
        <th>P95 wall</th>
        <th>Mediana CPU</th>
        <th>Mediana memorie</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="row in items"
        :key="`${row.model_type}-${row.language}`"
        class="row-link"
      >
        <td><strong>{{ MODEL_LABELS[row.model_type] }}</strong></td>
        <td><strong>{{ row.language }}</strong></td>
        <td>{{ row.run_count }}</td>
        <td>{{ fmtMs(row.median_wall_ms) }}</td>
        <td>{{ fmtMs(row.p95_wall_ms) }}</td>
        <td>{{ fmtMs(row.median_cpu_ms) }}</td>
        <td>{{ fmtMB(row.median_memory_mb) }}</td>
        <td class="cell-action">
          <router-link
            :to="{ name: 'benchmark-detail',
                   params: { model: row.model_type, language: row.language } }"
          >
            Detaliu →
          </router-link>
        </td>
      </tr>
      <tr v-if="items.length === 0">
        <td colspan="8" class="muted">Niciun benchmark încă. Rulează o simulare ca să vezi metrici.</td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.cell-action { text-align: right; }
.cell-action a {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border: 1px solid var(--c-border, #cbd5e1);
  border-radius: 0.3rem;
  text-decoration: none;
  font-size: 0.9rem;
}
.cell-action a:hover { background: var(--c-bg-hover, #f1f5f9); }
.row-link:hover { background: var(--c-bg-hover, #f8fafc); }
</style>
