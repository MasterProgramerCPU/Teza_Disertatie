import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { api, setToken, setUnauthorizedHandler, getToken } from "@/api/client";
import type { AuthResponse } from "@/types";
import router from "@/router";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(getToken());
  const userId = ref<string | null>(localStorage.getItem("emedicine.user_id"));
  const email = ref<string | null>(localStorage.getItem("emedicine.email"));

  const isAuthenticated = computed(() => !!token.value);

  function persistUser(id: string | null, mail: string | null) {
    if (id) localStorage.setItem("emedicine.user_id", id);
    else localStorage.removeItem("emedicine.user_id");
    if (mail) localStorage.setItem("emedicine.email", mail);
    else localStorage.removeItem("emedicine.email");
    userId.value = id;
    email.value = mail;
  }

  async function login(emailIn: string, password: string) {
    const auth = await api.post<AuthResponse>("/auth/login", {
      email: emailIn,
      password,
    });
    token.value = auth.token;
    setToken(auth.token);
    persistUser(auth.user_id, emailIn);
  }

  async function register(emailIn: string, password: string) {
    await api.post<{ id: string; email: string }>("/auth/register", {
      email: emailIn,
      password,
    });
  }

  function logout() {
    token.value = null;
    setToken(null);
    persistUser(null, null);
    router.push({ name: "login" });
  }

  setUnauthorizedHandler(() => {
    logout();
  });

  return { token, userId, email, isAuthenticated, login, register, logout };
});
