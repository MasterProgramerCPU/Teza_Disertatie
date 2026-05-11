<script setup lang="ts">
import { ref } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const email = ref("");
const password = ref("");
const submitting = ref(false);
const error = ref<string | null>(null);

async function submit() {
  error.value = null;
  submitting.value = true;
  try {
    await auth.login(email.value, password.value);
    const redirect = (route.query.redirect as string) || "/dashboard";
    router.push(redirect);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="card auth-card">
      <h1>Autentificare</h1>
      <form @submit.prevent="submit">
        <div class="col">
          <div>
            <label>Email</label>
            <input v-model="email" type="email" required :disabled="submitting" autofocus />
          </div>
          <div>
            <label>Parolă</label>
            <input v-model="password" type="password" required :disabled="submitting" />
          </div>
          <p v-if="error" class="alert error">{{ error }}</p>
          <button class="primary" type="submit" :disabled="submitting">
            {{ submitting ? "Se conectează..." : "Login" }}
          </button>
        </div>
      </form>
      <p class="muted" style="margin-top: 16px;">
        Nu ai cont? <router-link to="/register">Înregistrare</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 80px;
}
.auth-card { max-width: 400px; width: 100%; }
</style>
