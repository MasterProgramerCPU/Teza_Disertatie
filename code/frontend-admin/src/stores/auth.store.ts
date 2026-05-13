import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { api, setToken, setUnauthorizedHandler, getToken } from "@/api/client";
import type { AuthResponse } from "@/types";
import router from "@/router";

const LS_EMAIL = "emedicine-admin.email";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(getToken());
  const email = ref<string | null>(localStorage.getItem(LS_EMAIL));

  const isAuthenticated = computed(() => !!token.value);

  async function login(emailIn: string, password: string) {
    const auth = await api.post<AuthResponse>("/auth/login", {
      email: emailIn,
      password,
    });
    if (!auth.is_super_admin) {
      // tokenul nu se păstrează — credențialele sunt valide pentru SPA-ul user,
      // dar acest panou e rezervat super-adminilor.
      throw new Error("Acest cont nu are privilegii de super administrator.");
    }
    token.value = auth.token;
    setToken(auth.token);
    email.value = auth.email;
    localStorage.setItem(LS_EMAIL, auth.email);
  }

  function logout() {
    token.value = null;
    setToken(null);
    email.value = null;
    localStorage.removeItem(LS_EMAIL);
    router.push({ name: "login" });
  }

  setUnauthorizedHandler(() => logout());

  return { token, email, isAuthenticated, login, logout };
});
