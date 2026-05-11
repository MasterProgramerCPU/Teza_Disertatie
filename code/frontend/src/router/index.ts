import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { getToken } from "@/api/client";

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/dashboard" },
  { path: "/login", name: "login", component: () => import("@/pages/LoginPage.vue") },
  { path: "/register", name: "register", component: () => import("@/pages/RegisterPage.vue") },
  {
    path: "/dashboard",
    name: "dashboard",
    component: () => import("@/pages/DashboardPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/datasets",
    name: "datasets",
    component: () => import("@/pages/DatasetsPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/datasets/:id",
    name: "dataset-detail",
    component: () => import("@/pages/DatasetDetailPage.vue"),
    meta: { requiresAuth: true },
    props: true,
  },
  {
    path: "/simulations/new",
    name: "simulation-new",
    component: () => import("@/pages/NewSimulationPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/simulations/:id",
    name: "simulation-detail",
    component: () => import("@/pages/SimulationResultPage.vue"),
    meta: { requiresAuth: true },
    props: true,
  },
  {
    path: "/compare",
    name: "compare",
    component: () => import("@/pages/ComparePage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/benchmarks",
    name: "benchmarks",
    component: () => import("@/pages/BenchmarksPage.vue"),
    meta: { requiresAuth: true },
  },
  { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const requiresAuth = to.matched.some((r) => r.meta.requiresAuth);
  const hasToken = !!getToken();
  if (requiresAuth && !hasToken) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (!requiresAuth && hasToken && (to.name === "login" || to.name === "register")) {
    return { name: "dashboard" };
  }
});

export default router;
