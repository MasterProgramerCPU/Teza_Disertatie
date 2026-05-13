import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { api, setToken, setUnauthorizedHandler, getToken } from "@/api/client";
import type { AuthResponse, MeResponse } from "@/types";
import router from "@/router";

const LS_USER_ID = "emedicine.user_id";
const LS_EMAIL = "emedicine.email";
const LS_SUPER_ADMIN = "emedicine.is_super_admin";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(getToken());
  const userId = ref<string | null>(localStorage.getItem(LS_USER_ID));
  const email = ref<string | null>(localStorage.getItem(LS_EMAIL));
  const isSuperAdmin = ref<boolean>(localStorage.getItem(LS_SUPER_ADMIN) === "true");

  const isAuthenticated = computed(() => !!token.value);

  function persistUser(id: string | null, mail: string | null, superAdmin: boolean) {
    if (id) localStorage.setItem(LS_USER_ID, id);
    else localStorage.removeItem(LS_USER_ID);
    if (mail) localStorage.setItem(LS_EMAIL, mail);
    else localStorage.removeItem(LS_EMAIL);
    localStorage.setItem(LS_SUPER_ADMIN, superAdmin ? "true" : "false");
    userId.value = id;
    email.value = mail;
    isSuperAdmin.value = superAdmin;
  }

  async function login(emailIn: string, password: string) {
    const auth = await api.post<AuthResponse>("/auth/login", {
      email: emailIn,
      password,
    });
    token.value = auth.token;
    setToken(auth.token);
    persistUser(auth.user_id, auth.email, auth.is_super_admin);
  }

  async function register(emailIn: string, password: string) {
    await api.post<{ id: string; email: string }>("/auth/register", {
      email: emailIn,
      password,
    });
  }

  /** Citește profilul curent (folosit la load SPA pentru a sincroniza is_super_admin). */
  async function refreshMe(): Promise<MeResponse | null> {
    if (!token.value) return null;
    try {
      const me = await api.get<MeResponse>("/me");
      persistUser(me.id, me.email, me.is_super_admin);
      return me;
    } catch {
      return null;
    }
  }

  function logout() {
    token.value = null;
    setToken(null);
    persistUser(null, null, false);
    router.push({ name: "login" });
  }

  setUnauthorizedHandler(() => {
    logout();
  });

  return { token, userId, email, isSuperAdmin, isAuthenticated, login, register, refreshMe, logout };
});
