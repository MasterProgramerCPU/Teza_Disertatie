<script setup lang="ts">
import { computed } from "vue";
import { Line } from "vue-chartjs";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  LogarithmicScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  type ChartData,
  type ChartOptions,
} from "chart.js";

ChartJS.register(
  CategoryScale, LinearScale, LogarithmicScale, PointElement, LineElement, Tooltip, Legend,
);

interface Point {
  t_max: number;
  wall_ms: number;
}

const props = defineProps<{
  points: Point[];   // toate rulările individuale (t_max, wall_ms)
  height?: number;
}>();

interface Group {
  t_max: number;
  median: number;
  min: number;
  max: number;
  n: number;
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 === 0 ? (s[m - 1] + s[m]) / 2 : s[m];
}

const grouped = computed<Group[]>(() => {
  const by = new Map<number, number[]>();
  props.points.forEach((p) => {
    const arr = by.get(p.t_max) ?? [];
    arr.push(p.wall_ms);
    by.set(p.t_max, arr);
  });
  return Array.from(by.entries())
    .map(([t_max, xs]) => ({
      t_max,
      median: median(xs),
      min: Math.min(...xs),
      max: Math.max(...xs),
      n: xs.length,
    }))
    .sort((a, b) => a.t_max - b.t_max);
});

const chartData = computed<ChartData<"line">>(() => ({
  labels: grouped.value.map((g) => String(g.t_max)),
  datasets: [
    {
      label: "wall-time mediană (ms)",
      data: grouped.value.map((g) => g.median),
      borderColor: "rgba(0, 88, 238, 1)",
      backgroundColor: "rgba(0, 88, 238, 0.15)",
      fill: false,
      pointRadius: 4,
      pointBackgroundColor: "rgba(0, 88, 238, 1)",
      tension: 0,
      borderWidth: 2,
    },
    {
      label: "minim",
      data: grouped.value.map((g) => g.min),
      borderColor: "rgba(21, 130, 31, 0.6)",
      borderDash: [4, 4],
      fill: false,
      pointRadius: 0,
      tension: 0,
      borderWidth: 1,
    },
    {
      label: "maxim",
      data: grouped.value.map((g) => g.max),
      borderColor: "rgba(192, 0, 0, 0.6)",
      borderDash: [4, 4],
      fill: false,
      pointRadius: 0,
      tension: 0,
      borderWidth: 1,
    },
  ],
}));

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
      title: { display: true, text: "t_max (zile)", font: { family: "Tahoma", size: 12 } },
      grid: { color: "#d6d1bd" },
      ticks: { font: { family: "Tahoma", size: 11 } },
    },
    y: {
      type: "logarithmic",
      title: { display: true, text: "wall-time (ms, log)", font: { family: "Tahoma", size: 12 } },
      grid: { color: "#d6d1bd" },
      ticks: { font: { family: "Tahoma", size: 11 } },
    },
  },
}));
</script>

<template>
  <div class="chart-shell" :style="{ height: (height ?? 320) + 'px' }">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>

<style scoped>
.chart-shell {
  padding: 8px;
  background: #ffffff;
  border: 1px inset var(--c-border);
}
</style>
