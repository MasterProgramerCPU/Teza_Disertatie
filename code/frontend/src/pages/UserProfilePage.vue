<script setup lang="ts">
import { onMounted, ref, watch, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useProfileStore } from "@/stores/profile.store";
import UserAvatar from "@/components/UserAvatar.vue";
import type { UserProfile, CollaboratorsByStudy } from "@/types";

const route = useRoute();
const router = useRouter();
const profile = useProfileStore();

const target = ref<UserProfile | null>(null);
const loadError = ref<string | null>(null);
const loading = ref(false);

const targetId = computed(() => String(route.params.userId ?? ""));

// Studiile pe care le impart cu acest utilizator, derivate din lista mea de
// colaboratori (deja incarcata de pagina /profile).
const sharedStudies = computed<CollaboratorsByStudy[]>(() => {
  return profile.collaborators.filter((g) =>
    g.members.some((m) => m.user_id === targetId.value),
  );
});

async function load() {
  loadError.value = null;
  loading.value = true;
  try {
    target.value = await profile.fetchUserProfile(targetId.value);
    if (profile.collaborators.length === 0) {
      await profile.fetchCollaborators();
    }
  } catch (e) {
    loadError.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(targetId, load);
</script>

<template>
  <div class="page">
    <button type="button" class="btn back" @click="router.back()">&larr; Înapoi</button>

    <div v-if="loading" class="muted">Se încarcă profilul…</div>
    <div v-else-if="loadError" class="error">{{ loadError }}</div>

    <template v-else-if="target">
      <section class="card">
        <div class="head">
          <UserAvatar
            :user-id="target.id"
            :email="target.email"
            :full-name="target.full_name"
            :has-avatar="target.has_avatar"
            :size="128"
          />
          <div class="head-text">
            <h1>{{ target.full_name || target.email }}</h1>
            <div class="muted">{{ target.email }}</div>
            <div v-if="target.affiliation" class="affil">{{ target.affiliation }}</div>
            <div v-if="target.is_super_admin" class="sa-badge">Super administrator</div>
          </div>
        </div>

        <div v-if="target.bio" class="bio">
          <h2>Bio</h2>
          <p>{{ target.bio }}</p>
        </div>
      </section>

      <section class="card">
        <h2>Studii pe care le împărțim</h2>
        <p class="muted" v-if="sharedStudies.length === 0">
          Nu am detectat studii comune. Probabil ești super-admin sau membership-urile s-au schimbat recent.
        </p>
        <ul class="studies">
          <li v-for="g in sharedStudies" :key="g.study.id">
            <strong>{{ g.study.name }}</strong>
            <span class="badge">{{ g.study.disease_code }}</span>
            <span class="muted small">
              eu: {{ g.my_role }} ·
              el/ea: {{ g.members.find((m) => m.user_id === targetId)?.role }}
            </span>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page {
  max-width: 880px;
  margin: 0 auto;
  padding: 16px;
}

.btn {
  display: inline-block;
  padding: 4px 10px;
  border: 1px solid var(--btn-border);
  background: linear-gradient(180deg, var(--btn-bg-1) 0%, var(--btn-bg-2) 48%, var(--btn-bg-3) 100%);
  box-shadow: inset 1px 1px 0 var(--btn-inset-light), inset -1px -1px 0 var(--btn-inset-dark);
  color: var(--btn-text);
  font-size: 12px;
  cursor: pointer;
  margin-bottom: 10px;
}

.card {
  background: var(--c-surface);
  color: var(--c-text);
  border: 1px solid var(--c-border-dark);
  box-shadow: inset 1px 1px 0 var(--c-border-light), inset -1px -1px 0 var(--c-border), var(--shadow-sm);
  padding: 14px;
  margin-bottom: 14px;
}

.card h2 {
  margin: 0 0 8px;
  font-size: 14px;
  border-bottom: 1px solid var(--c-border);
  padding-bottom: 4px;
  color: var(--c-text-strong);
}

.head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.head-text h1 {
  margin: 0 0 4px;
  font-size: 18px;
}

.affil {
  font-size: 13px;
  color: var(--c-text);
  margin-top: 2px;
}

.sa-badge {
  display: inline-block;
  margin-top: 4px;
  font-size: 10px;
  background: linear-gradient(180deg, var(--btn-danger-1) 0%, var(--btn-danger-3) 100%);
  color: #fff;
  padding: 2px 6px;
  border: 1px solid var(--btn-danger-3);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.muted { color: var(--c-text-muted); }
.muted.small { font-size: 11px; }

.bio {
  margin-top: 8px;
}

.bio p {
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.4;
}

.studies {
  list-style: none;
  padding: 0;
  margin: 0;
}

.studies li {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 4px;
  border-bottom: 1px dashed var(--c-border);
}

.studies li:last-child { border-bottom: none; }

.badge {
  display: inline-block;
  background: var(--c-surface-soft);
  color: var(--c-text);
  border: 1px solid var(--c-border);
  padding: 1px 6px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.error {
  background: rgba(176, 0, 0, 0.18);
  border: 1px solid var(--c-danger);
  padding: 6px 10px;
  font-size: 12px;
  color: var(--c-danger);
}
</style>
