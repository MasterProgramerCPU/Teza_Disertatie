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
  s: "9, 105, 218",
  i: "207, 34, 46",
  d: "130, 80, 223",
  a: "191, 135, 0",
  r: "31, 111, 235",
  t: "188, 76, 0",
  h: "26, 127, 55",
};

const ORDER = ["s", "i", "d", "a", "r", "t", "h"];

function dash(style?: string): number[] {
  if (style === "dashed") return [8, 6];
  if (style === "dotted") return [2, 4];
  return [];
}

function compartmentKeys(points: SimulationResultPoint[]): string[] {
  const seen = new Set<string>();
  points.forEach((p) => Object.keys(p.compartments).forEach((key) => seen.add(key)));
  const ordered = ORDER.filter((key) => seen.has(key));
  const extra = Array.from(seen).filter((key) => !ORDER.includes(key)).sort();
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
    legend: { position: "bottom" },
    tooltip: { mode: "index", intersect: false },
  },
  scales: {
    x: { title: { display: true, text: "t (zile)" } },
    y: { title: { display: true, text: "populație" }, beginAtZero: true },
  },
}));
</script>

<template>
  <div :style="{ height: (height ?? 420) + 'px' }">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>
