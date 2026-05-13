<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useStudiesStore } from "@/stores/studies.store";
import { useAuthStore } from "@/stores/auth.store";

const studies = useStudiesStore();
const auth = useAuthStore();
const router = useRouter();

onMounted(() => studies.fetchMine());

function selectStudy(id: string) {
  studies.setCurrent(id);
  router.push({ name: "dashboard" });
}

function roleLabel(role: string): string {
  const map: Record<string, string> = {
    admin: "Administrator",
    researcher: "Cercetător",
    contributor: "Contributor",
    viewer: "Vizualizator",
  };
  return map[role] ?? role;
}
</script>

<template>
  <div class="page">
    <header class="header">
      <h1>Studiile mele</h1>
      <router-link to="/studies/new" class="btn primary">+ Studiu nou</router-link>
    </header>

    <p v-if="auth.isSuperAdmin" class="muted">
      Ești super-administrator — vezi <strong>toate studiile</strong> din sistem,
      indiferent de calitatea de membru.
    </p>

    <p v-if="studies.loading">Se încarcă…</p>
    <p v-else-if="studies.error" class="error">{{ studies.error }}</p>

    <div v-else-if="studies.memberships.length === 0" class="empty">
      <p>Nu ești încă membru al unui studiu.</p>
      <p class="muted">Creează unul nou sau roagă un administrator să te adauge la un studiu existent.</p>
    </div>

    <ul v-else class="list">
      <li
        v-for="m in studies.memberships"
        :key="m.study.id"
        class="card"
        :class="{ active: m.study.id === studies.currentStudyId }"
      >
        <div class="card-body" @click="selectStudy(m.study.id)">
          <div class="card-title">
            <strong>{{ m.study.name }}</strong>
            <span class="badge" :class="`role-${m.role}`">{{ roleLabel(m.role) }}</span>
          </div>
          <div class="meta">
            <span><code>{{ m.study.disease_code }}</code></span>
            <span class="muted">creat {{ new Date(m.study.created_at).toLocaleDateString() }}</span>
          </div>
          <p v-if="m.study.description" class="desc">{{ m.study.description }}</p>
        </div>
        <div v-if="m.role === 'admin'" class="card-actions">
          <router-link :to="{ name: 'study-manage', params: { id: m.study.id } }" class="btn small">Management</router-link>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.page { max-width: 960px; margin: 0 auto; padding: 8px; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.list { list-style: none; padding: 0; margin: 0; display: grid; gap: 12px; }
.card {
  background: linear-gradient(180deg, #f8f6ed 0%, #ece9d8 100%);
  border: 1px solid var(--c-border-dark);
  border-radius: 0;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #808080, var(--shadow-sm);
}
.card.active { border-color: #003c74; box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #003c74, 0 0 0 2px rgba(10, 70, 196, .35); }
.card-body { flex: 1; cursor: pointer; }
.card-title { display: flex; gap: 12px; align-items: center; font-size: 16px; margin-bottom: 4px; }
.meta { display: flex; gap: 12px; align-items: center; font-size: 13px; color: var(--c-text-muted); }
.desc { margin: 8px 0 0; color: var(--c-text-muted); font-size: 14px; }
.badge {
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px;
  text-transform: uppercase; letter-spacing: 0.5px;
  border-radius: 0;
}
.role-admin { background: #ffc9c9; color: #800000; border-color: #b00000; }
.role-researcher { background: #c9e1ff; color: #003399; border-color: #0a46c4; }
.role-contributor { background: #c9f0c9; color: #07540d; border-color: #15821f; }
.role-viewer { background: #ffffff; color: #4b4b4b; border-color: #808080; }
.empty { text-align: center; padding: 48px; color: var(--c-text-muted); background: #ffffff; border: 1px inset #808080; }
.error { color: #c53030; }
.btn.small { font-size: 13px; padding: 4px 10px; }
</style>
