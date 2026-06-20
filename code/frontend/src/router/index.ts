import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { getToken } from "@/api/client";
import { useStudiesStore } from "@/stores/studies.store";

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/dashboard" },
  { path: "/login", name: "login", component: () => import("@/pages/LoginPage.vue") },
  { path: "/register", name: "register", component: () => import("@/pages/RegisterPage.vue") },
  {
    path: "/studies",
    name: "studies",
    component: () => import("@/pages/StudiesPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/studies/new",
    name: "study-new",
    component: () => import("@/pages/CreateStudyPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/studies/:id/manage",
    name: "study-manage",
    component: () => import("@/pages/StudyManagementPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true, requiresAdmin: true },
    props: true,
  },
  {
    path: "/dashboard",
    name: "dashboard",
    component: () => import("@/pages/DashboardPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
  },
  {
    path: "/datasets",
    name: "datasets",
    component: () => import("@/pages/DatasetsPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
  },
  {
    path: "/datasets/:id",
    name: "dataset-detail",
    component: () => import("@/pages/DatasetDetailPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
    props: true,
  },
  {
    path: "/simulations/new",
    name: "simulation-new",
    component: () => import("@/pages/NewSimulationPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
  },
  {
    path: "/simulations/:id",
    name: "simulation-detail",
    component: () => import("@/pages/SimulationResultPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
    props: true,
  },
  {
    path: "/compare",
    name: "compare",
    component: () => import("@/pages/ComparePage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
  },
  {
    path: "/benchmarks",
    name: "benchmarks",
    component: () => import("@/pages/BenchmarksPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
  },
  {
    path: "/map",
    name: "map",
    component: () => import("@/pages/MapPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
  },
  {
    path: "/benchmarks/:model/:language",
    name: "benchmark-detail",
    component: () => import("@/pages/BenchmarkDetailPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
    props: true,
  },
  {
    path: "/script-editor",
    name: "script-editor",
    component: () => import("@/pages/ScriptEditorPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true },
  },
  {
    path: "/owner-dashboard",
    name: "owner-dashboard",
    component: () => import("@/pages/StudyOwnerDashboardPage.vue"),
    meta: { requiresAuth: true, requiresStudy: true, requiresAdmin: true },
  },
  {
    path: "/profile",
    name: "profile",
    component: () => import("@/pages/ProfilePage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/users/:userId",
    name: "user-profile",
    component: () => import("@/pages/UserProfilePage.vue"),
    meta: { requiresAuth: true },
    props: true,
  },
  { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const requiresAuth = to.matched.some((r) => r.meta.requiresAuth);
  const requiresStudy = to.matched.some((r) => r.meta.requiresStudy);
  const requiresAdmin = to.matched.some((r) => r.meta.requiresAdmin);
  const hasToken = !!getToken();

  if (requiresAuth && !hasToken) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (!requiresAuth && hasToken && (to.name === "login" || to.name === "register")) {
    return { name: "dashboard" };
  }

  if (requiresStudy && hasToken) {
    const studies = useStudiesStore();
    if (studies.memberships.length === 0) {
      await studies.fetchMine();
    }
    if (!studies.currentStudyId) {
      return { name: "studies" };
    }
    if (requiresAdmin && studies.currentRole !== "admin") {
      return { name: "studies" };
    }
  }
});

export default router;
