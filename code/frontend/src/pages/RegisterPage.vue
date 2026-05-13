<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";

const router = useRouter();
const auth = useAuthStore();

const email = ref("");
const password = ref("");
const submitting = ref(false);
const error = ref<string | null>(null);

async function submit() {
  if (password.value.length < 8) {
    error.value = "parola trebuie să aibă cel puțin 8 caractere";
    return;
  }
  error.value = null;
  submitting.value = true;
  try {
    await auth.register(email.value, password.value);
    await auth.login(email.value, password.value);
    router.push("/dashboard");
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
      <h1>Înregistrare</h1>
      <form @submit.prevent="submit">
        <div class="col">
          <div>
            <label>Email</label>
            <input v-model="email" type="email" required :disabled="submitting" autofocus />
          </div>
          <div>
            <label>Parolă (min. 8 caractere)</label>
            <input v-model="password" type="password" required minlength="8" :disabled="submitting" />
          </div>
          <p v-if="error" class="alert error">{{ error }}</p>
          <button class="primary" type="submit" :disabled="submitting">
            {{ submitting ? "Se creează contul..." : "Creează cont" }}
          </button>
        </div>
      </form>
      <p class="muted" style="margin-top: 16px;">
        Ai deja cont? <router-link to="/login">Login</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page { display: flex; justify-content: center; padding-top: 56px; }
.auth-card { max-width: 420px; width: 100%; }
</style>
