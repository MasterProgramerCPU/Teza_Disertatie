<script setup lang="ts">
import { computed } from "vue";
import { Line } from "vue-chartjs";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
  type ChartData,
  type ChartOptions,
} from "chart.js";
import { COMPARTMENT_LABELS } from "@/model-presets";
import type { SimulationResultPoint } from "@/types";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler);

interface Series {
  label: string;
  points: SimulationResultPoint[];
  style?: "solid" | "dashed" | "dotted";
}

const props = defineProps<{
  series: Series[];
  height?: number;
}>();

const COLORS: Record<string, string> = {
  s: "0, 88, 238",
  e: "96, 96, 96",
  i: "192, 0, 0",
  d: "96, 40, 180",
  a: "156, 101, 0",
  r: "21, 130, 31",
  t: "196, 91, 0",
  h: "0, 92, 48",
  observed: "0, 88, 238",
  fitted: "21, 130, 31",
  predicted: "192, 0, 0",
};

function dash(style?: string): number[] {
  if (style === "dashed") return [8, 6];
  if (style === "dotted") return [2, 4];
  return [];
}

function compartmentKeys(points: SimulationResultPoint[]): string[] {
  const seen = new Set<string>();
  points.forEach((p) => Object.keys(p.compartments).forEach((key) => seen.add(key)));
  const order = seen.has("e") && !seen.has("d") && !seen.has("a") && !seen.has("t") && !seen.has("h")
    ? ["s", "e", "i", "r"]
    : ["s", "i", "d", "a", "r", "t", "h", "e"];
  const lstmOrder = ["observed", "fitted", "predicted"];
  if (lstmOrder.some((key) => seen.has(key))) {
    return [
      ...lstmOrder.filter((key) => seen.has(key)),
      ...Array.from(seen).filter((key) => !lstmOrder.includes(key)).sort(),
    ];
  }
  const ordered = order.filter((key) => seen.has(key));
  const extra = Array.from(seen).filter((key) => !order.includes(key)).sort();
  return [...ordered, ...extra];
}

const chartData = computed<ChartData<"line">>(() => {
  const allT = new Set<number>();
  props.series.forEach((s) => s.points.forEach((p) => allT.add(p.t)));
  const labels = Array.from(allT).sort((a, b) => a - b);

  const datasets = props.series.flatMap((s, idx) => {
    const opacity = idx === 0 ? 1 : 0.82;
    const map = new Map(s.points.map((p) => [p.t, p]));
    const suffix = props.series.length > 1 ? ` (${s.label})` : "";
    return compartmentKeys(s.points).map((key) => ({
      label: `${COMPARTMENT_LABELS[key] ?? key}${suffix}`,
      data: labels.map((t) => map.get(t)?.compartments[key] ?? null),
      borderColor: `rgba(${COLORS[key] ?? "87, 96, 106"}, ${opacity})`,
      backgroundColor: "transparent",
      borderWidth: 2,
      borderDash: dash(s.style),
      pointRadius: 0,
      tension: 0.1,
    }));
  });

  return { labels: labels.map(String), datasets };
});

const chartOptions = computed<ChartOptions<"line">>(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { intersect: false, mode: "index" },
  plugins: {
    legend: {
      position: "bottom",
      labels: { font: { family: "Tahoma", size: 11 }, boxWidth: 18 },
    },
    tooltip: {
      mode: "index",
      intersect: false,
      titleFont: { family: "Tahoma", size: 12 },
      bodyFont: { family: "Tahoma", size: 12 },
      backgroundColor: "rgba(255, 255, 225, 0.96)",
      titleColor: "#000000",
      bodyColor: "#000000",
      borderColor: "#808080",
      borderWidth: 1,
    },
  },
  scales: {
    x: {
      title: { display: true, text: "t (zile)", font: { family: "Tahoma", size: 12 } },
      grid: { color: "#d6d1bd" },
      ticks: { font: { family: "Tahoma", size: 11 } },
    },
    y: {
      title: { display: true, text: "populație", font: { family: "Tahoma", size: 12 } },
      beginAtZero: true,
      grid: { color: "#d6d1bd" },
      ticks: { font: { family: "Tahoma", size: 11 } },
    },
  },
}));
</script>

<template>
  <div class="chart-shell" :style="{ height: (height ?? 420) + 'px' }">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>

<style scoped>
.chart-shell {
  padding: 8px;
  /* Pastram fond alb in ambele teme — canvas-ul Chart.js deseneaza axe in negru */
  background: #ffffff;
  border: 1px inset var(--c-border);
}
</style>
