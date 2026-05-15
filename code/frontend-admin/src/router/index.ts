import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import { getToken } from "@/api/client";

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/dashboard" },
  { path: "/login", name: "login", component: () => import("@/pages/LoginPage.vue") },
  {
    path: "/dashboard",
    name: "dashboard",
    component: () => import("@/pages/DashboardPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/users",
    name: "users",
    component: () => import("@/pages/UsersPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/studies",
    name: "studies",
    component: () => import("@/pages/StudiesPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/studies/:id",
    name: "study-detail",
    component: () => import("@/pages/StudyDetailPage.vue"),
    meta: { requiresAuth: true },
  },
  {
    path: "/activity",
    name: "activity",
    component: () => import("@/pages/ActivityPage.vue"),
    meta: { requiresAuth: true },
  },
  { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
];

const router = createRouter({
  // SPA standalone la admin.sir-workbench.ro — istoricul porneste de la root.
  history: createWebHistory("/"),
  routes,
});

router.beforeEach((to) => {
  const requiresAuth = to.matched.some((r) => r.meta.requiresAuth);
  const hasToken = !!getToken();
  if (requiresAuth && !hasToken) return { name: "login" };
  if (!requiresAuth && hasToken && to.name === "login") return { name: "dashboard" };
});

export default router;
