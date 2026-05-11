<script setup lang="ts">
import { computed } from "vue";
import { Line } from "vue-chartjs";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  type ChartData,
  type ChartOptions,
} from "chart.js";
import type { SimulationResultPoint } from "@/types";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

interface Series {
  label: string;
  points: SimulationResultPoint[];
  style?: "solid" | "dashed" | "dotted";
}

const props = defineProps<{
  series: Series[];
  height?: number;
}>();

function dash(style?: string): number[] {
  if (style === "dashed") return [8, 6];
  if (style === "dotted") return [2, 4];
  return [];
}

const chartData = computed<ChartData<"line">>(() => {
  const allT = new Set<number>();
  props.series.forEach((s) => s.points.forEach((p) => allT.add(p.t)));
  const labels = Array.from(allT).sort((a, b) => a - b);

  const datasets = props.series.flatMap((s, idx) => {
    const opacity = idx === 0 ? 1 : 0.85;
    const map = new Map(s.points.map((p) => [p.t, p]));
    const get = (t: number, field: "s" | "i" | "r") => map.get(t)?.[field] ?? null;
    const suffix = props.series.length > 1 ? ` (${s.label})` : "";
    return [
      {
        label: "S" + suffix,
        data: labels.map((t) => get(t, "s")),
        borderColor: `rgba(9, 105, 218, ${opacity})`,
        backgroundColor: "transparent",
        borderWidth: 2,
        borderDash: dash(s.style),
        pointRadius: 0,
        tension: 0.1,
      },
      {
        label: "I" + suffix,
        data: labels.map((t) => get(t, "i")),
        borderColor: `rgba(207, 34, 46, ${opacity})`,
        backgroundColor: "transparent",
        borderWidth: 2,
        borderDash: dash(s.style),
        pointRadius: 0,
        tension: 0.1,
      },
      {
        label: "R" + suffix,
        data: labels.map((t) => get(t, "r")),
        borderColor: `rgba(26, 127, 55, ${opacity})`,
        backgroundColor: "transparent",
        borderWidth: 2,
        borderDash: dash(s.style),
        pointRadius: 0,
        tension: 0.1,
      },
    ];
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
    y: { title: { display: true, text: "populatie" }, beginAtZero: true },
  },
}));
</script>

<template>
  <div :style="{ height: (height ?? 420) + 'px' }">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>
