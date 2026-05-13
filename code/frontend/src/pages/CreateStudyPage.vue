<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useStudiesStore } from "@/stores/studies.store";

const studies = useStudiesStore();
const router = useRouter();

const name = ref("");
const diseaseCode = ref("");
const description = ref("");
const submitting = ref(false);
const error = ref<string | null>(null);

async function submit() {
  if (!name.value.trim() || !diseaseCode.value.trim()) {
    error.value = "Numele și codul bolii sunt obligatorii";
    return;
  }
  submitting.value = true;
  error.value = null;
  try {
    await studies.create(name.value.trim(), diseaseCode.value.trim(), description.value.trim());
    router.push({ name: "dashboard" });
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="page">
    <h1>Studiu nou</h1>
    <p class="muted">
      Creezi un studiu epidemiologic dedicat unei singure boli. Vei deveni automat
      <strong>administrator</strong> al studiului și vei putea adăuga alți membri ulterior.
    </p>

    <form @submit.prevent="submit" class="form">
      <label>
        Nume studiu
        <input v-model="name" required placeholder="ex.: COVID-19, valul 1, primăvara 2020" />
      </label>
      <label>
        Cod boală
        <input v-model="diseaseCode" required placeholder="ex.: covid19, flu-h1n1, measles" />
        <span class="hint">Identificator scurt — folosit pentru filtrare și raportare.</span>
      </label>
      <label>
        Descriere (opțional)
        <textarea v-model="description" rows="3" placeholder="Context, obiective, perioada de analiză…"></textarea>
      </label>

      <p v-if="error" class="error">{{ error }}</p>

      <div class="actions">
        <router-link to="/studies" class="btn">Anulează</router-link>
        <button type="submit" class="btn primary" :disabled="submitting">
          {{ submitting ? "Se creează…" : "Creează studiu" }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.page { max-width: 600px; margin: 0 auto; padding: 24px; }
.form { display: flex; flex-direction: column; gap: 16px; margin-top: 16px; }
.form label { display: flex; flex-direction: column; gap: 6px; font-weight: 500; }
.form input, .form textarea {
  padding: 8px 12px; border: 1px solid var(--c-border); border-radius: var(--radius);
  font-family: inherit; font-size: 14px; background: var(--c-surface);
}
.form textarea { resize: vertical; }
.hint { font-weight: 400; font-size: 12px; color: var(--c-text-muted); }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.error { color: #c53030; margin: 0; }
.btn { padding: 8px 16px; border-radius: var(--radius); text-decoration: none; cursor: pointer; border: 1px solid var(--c-border); background: var(--c-surface); color: var(--c-text); }
.btn.primary { background: var(--c-primary); color: white; border-color: var(--c-primary); }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
