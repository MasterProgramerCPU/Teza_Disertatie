<script setup lang="ts">
import { computed } from "vue";
import { Bar } from "vue-chartjs";
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  type ChartData,
  type ChartOptions,
} from "chart.js";

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip, Legend);

const props = defineProps<{
  values: number[];
  bins?: number;
  unit?: string;
  height?: number;
}>();

function fmtAxis(v: number, unit?: string): string {
  if (unit === "ms" && v >= 1000) return (v / 1000).toFixed(1) + " s";
  if (unit === "ms") return v.toFixed(0) + " ms";
  if (unit === "MB") return v.toFixed(0) + " MB";
  return v.toFixed(0);
}

const chartData = computed<ChartData<"bar">>(() => {
  const v = props.values;
  if (v.length === 0) return { labels: [], datasets: [] };

  const min = Math.min(...v);
  const max = Math.max(...v);
  const k = Math.max(3, Math.min(props.bins ?? Math.ceil(Math.sqrt(v.length)), 20));

  if (max === min) {
    return {
      labels: [fmtAxis(min, props.unit)],
      datasets: [{
        label: "rulări",
        data: [v.length],
        backgroundColor: "rgba(0, 88, 238, 0.7)",
        borderColor: "rgba(0, 88, 238, 1)",
        borderWidth: 1,
      }],
    };
  }

  const step = (max - min) / k;
  const buckets = new Array(k).fill(0);
  const labels: string[] = [];
  for (let i = 0; i < k; i++) {
    const lo = min + i * step;
    const hi = i === k - 1 ? max : lo + step;
    labels.push(`${fmtAxis(lo, props.unit)} – ${fmtAxis(hi, props.unit)}`);
  }
  v.forEach((val) => {
    let idx = Math.floor((val - min) / step);
    if (idx >= k) idx = k - 1;
    if (idx < 0) idx = 0;
    buckets[idx] += 1;
  });

  return {
    labels,
    datasets: [{
      label: "rulări",
      data: buckets,
      backgroundColor: "rgba(0, 88, 238, 0.7)",
      borderColor: "rgba(0, 88, 238, 1)",
      borderWidth: 1,
    }],
  };
});

const chartOptions = computed<ChartOptions<"bar">>(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
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
      title: { display: true, text: "interval", font: { family: "Tahoma", size: 12 } },
      grid: { color: "#d6d1bd" },
      ticks: {
        font: { family: "Tahoma", size: 10 },
        maxRotation: 35,
        minRotation: 0,
      },
    },
    y: {
      title: { display: true, text: "număr rulări", font: { family: "Tahoma", size: 12 } },
      beginAtZero: true,
      grid: { color: "#d6d1bd" },
      ticks: { stepSize: 1, font: { family: "Tahoma", size: 11 } },
    },
  },
}));
</script>

<template>
  <div class="chart-shell" :style="{ height: (height ?? 300) + 'px' }">
    <Bar v-if="values.length > 0" :data="chartData" :options="chartOptions" />
    <p v-else class="muted">Nu sunt date.</p>
  </div>
</template>

<style scoped>
.chart-shell {
  padding: 8px;
  background: #ffffff;
  border: 1px inset var(--c-border);
}
</style>
