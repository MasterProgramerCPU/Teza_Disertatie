<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";

const auth = useAuthStore();
const router = useRouter();

const email = ref("");
const password = ref("");
const submitting = ref(false);
const error = ref<string | null>(null);

async function submit() {
  error.value = null;
  submitting.value = true;
  try {
    await auth.login(email.value, password.value);
    router.push({ name: "dashboard" });
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="header">
        <span class="badge">SA</span>
        <h1>Admin Console</h1>
        <p class="muted">
          Acces rezervat super-administratorilor. Conturile utilizatorilor obișnuiți
          se autentifică în <a href="http://sir-workbench.ro">aplicația principală</a>.
        </p>
      </div>

      <form @submit.prevent="submit" class="form">
        <label>
          Email
          <input v-model="email" type="email" autocomplete="email" required :disabled="submitting" />
        </label>
        <label>
          Parolă
          <input v-model="password" type="password" autocomplete="current-password" required :disabled="submitting" />
        </label>
        <p v-if="error" class="error">{{ error }}</p>
        <button class="primary" type="submit" :disabled="submitting">
          {{ submitting ? "Se conectează…" : "Autentificare" }}
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(ellipse at 18% 78%, rgba(95, 172, 62, 0.95) 0 18%, transparent 19%),
    radial-gradient(ellipse at 78% 82%, rgba(60, 142, 45, 0.9) 0 22%, transparent 23%),
    linear-gradient(180deg, #1f68db 0%, #61b7ff 48%, #71b950 49%, #2f7d27 100%);
}
.login-card {
  background: var(--c-surface);
  border: 1px solid #404040;
  border-radius: 0;
  padding: 28px;
  width: 400px;
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #808080, 4px 4px 0 rgba(0, 0, 0, 0.28);
}
.header { text-align: center; margin-bottom: 24px; }
.header h1 { margin: 8px 0; }
.badge {
  display: inline-block;
  background: linear-gradient(180deg, #ff7777 0%, #b00000 100%);
  color: white;
  padding: 4px 10px;
  border-radius: 0;
  border: 1px solid #7a0000;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.form { display: flex; flex-direction: column; gap: 14px; }
.form label { display: flex; flex-direction: column; gap: 4px; font-weight: 500; font-size: 13px; }
.form input { padding: 8px 12px; font-size: 14px; }
.error { color: var(--c-primary); margin: 0; }
</style>
