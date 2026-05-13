import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";
import type { AdminStats, Study, User } from "@/types";

export const useAdminStore = defineStore("admin", () => {
  const stats = ref<AdminStats | null>(null);
  const users = ref<User[]>([]);
  const studies = ref<Study[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchStats() {
    try {
      stats.value = await api.get<AdminStats>("/admin/stats");
    } catch (e) {
      error.value = (e as Error).message;
    }
  }

  async function fetchUsers() {
    loading.value = true;
    try {
      users.value = (await api.get<User[] | null>("/admin/users")) ?? [];
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function fetchStudies() {
    loading.value = true;
    try {
      studies.value = (await api.get<Study[] | null>("/admin/studies")) ?? [];
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function setSuperAdmin(userId: string, isSuperAdmin: boolean) {
    await api.patch<unknown>(`/admin/users/${userId}/super-admin`, {
      is_super_admin: isSuperAdmin,
    });
    const u = users.value.find((u) => u.id === userId);
    if (u) u.is_super_admin = isSuperAdmin;
  }

  return { stats, users, studies, loading, error, fetchStats, fetchUsers, fetchStudies, setSuperAdmin };
});
