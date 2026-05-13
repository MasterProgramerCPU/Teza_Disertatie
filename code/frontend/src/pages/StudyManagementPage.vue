<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useStudiesStore } from "@/stores/studies.store";
import type { Study, StudyMember, StudyRole } from "@/types";

const route = useRoute();
const router = useRouter();
const studies = useStudiesStore();

const studyId = computed(() => route.params.id as string);
const study = ref<Study | null>(null);
const members = ref<StudyMember[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const editName = ref("");
const editDiseaseCode = ref("");
const editDescription = ref("");

const newEmail = ref("");
const newRole = ref<StudyRole>("viewer");
const addingMember = ref(false);

async function load() {
  loading.value = true;
  try {
    await studies.fetchMine();
    const m = studies.memberships.find((x) => x.study.id === studyId.value);
    if (!m) {
      error.value = "Studiul nu există sau nu ai acces";
      return;
    }
    study.value = m.study;
    editName.value = m.study.name;
    editDiseaseCode.value = m.study.disease_code;
    editDescription.value = m.study.description ?? "";
    members.value = await studies.listMembers(studyId.value);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function saveMetadata() {
  try {
    const updated = await studies.update(
      studyId.value,
      editName.value.trim(),
      editDiseaseCode.value.trim(),
      editDescription.value.trim(),
    );
    study.value = updated;
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function deleteStudy() {
  if (!confirm("Sigur ștergi studiul? Toate dataseturile și simulările vor fi pierdute.")) return;
  try {
    await studies.remove(studyId.value);
    router.push({ name: "studies" });
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function addMember() {
  if (!newEmail.value.trim()) return;
  addingMember.value = true;
  error.value = null;
  try {
    const m = await studies.addMember(studyId.value, newEmail.value.trim(), newRole.value);
    members.value.push(m);
    newEmail.value = "";
    newRole.value = "viewer";
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    addingMember.value = false;
  }
}

async function changeRole(member: StudyMember, role: StudyRole) {
  try {
    await studies.updateMemberRole(studyId.value, member.user_id, role);
    member.role = role;
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function removeMember(member: StudyMember) {
  if (!confirm(`Scoți ${member.email} din studiu?`)) return;
  try {
    await studies.removeMember(studyId.value, member.user_id);
    members.value = members.value.filter((m) => m.user_id !== member.user_id);
  } catch (e) {
    error.value = (e as Error).message;
  }
}
</script>

<template>
  <div class="page">
    <header class="header">
      <router-link to="/studies" class="back">← Studii</router-link>
      <h1 v-if="study">{{ study.name }}</h1>
      <h1 v-else>Management studiu</h1>
    </header>

    <p v-if="loading">Se încarcă…</p>
    <p v-if="error" class="error">{{ error }}</p>

    <section v-if="study" class="card">
      <h2>Metadata</h2>
      <form @submit.prevent="saveMetadata" class="form">
        <label>Nume<input v-model="editName" required /></label>
        <label>Cod boală<input v-model="editDiseaseCode" required /></label>
        <label>Descriere<textarea v-model="editDescription" rows="3"></textarea></label>
        <button class="btn primary">Salvează</button>
      </form>
    </section>

    <section v-if="study" class="card">
      <h2>Membri ({{ members.length }})</h2>
      <table class="members">
        <thead><tr><th>Email</th><th>Rol</th><th>Din</th><th></th></tr></thead>
        <tbody>
          <tr v-for="m in members" :key="m.user_id">
            <td>{{ m.email }}</td>
            <td>
              <select :value="m.role" @change="changeRole(m, ($event.target as HTMLSelectElement).value as StudyRole)">
                <option value="admin">Administrator</option>
                <option value="researcher">Cercetător</option>
                <option value="contributor">Contributor</option>
                <option value="viewer">Vizualizator</option>
              </select>
            </td>
            <td class="muted">{{ new Date(m.joined_at).toLocaleDateString() }}</td>
            <td><button @click="removeMember(m)" class="btn danger small">Scoate</button></td>
          </tr>
        </tbody>
      </table>

      <h3>Adaugă membru</h3>
      <form @submit.prevent="addMember" class="add-form">
        <input v-model="newEmail" type="email" placeholder="email@exemplu.ro" required />
        <select v-model="newRole">
          <option value="admin">Administrator</option>
          <option value="researcher">Cercetător</option>
          <option value="contributor">Contributor</option>
          <option value="viewer">Vizualizator</option>
        </select>
        <button class="btn" :disabled="addingMember">{{ addingMember ? "..." : "Adaugă" }}</button>
      </form>
    </section>

    <section v-if="study" class="card danger-zone">
      <h2>Zonă de risc</h2>
      <p class="muted">Ștergerea studiului e ireversibilă — pierzi toate dataseturile, simulările și asocierile.</p>
      <button @click="deleteStudy" class="btn danger">Șterge studiul</button>
    </section>
  </div>
</template>

<style scoped>
.page { max-width: 820px; margin: 0 auto; padding: 8px; }
.header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.back { color: #000080; text-decoration: underline; }
.card {
  background: var(--c-surface); border: 1px solid var(--c-border-dark);
  border-radius: 0; padding: 20px; margin-bottom: 16px;
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #808080, var(--shadow-sm);
}
.card h2 { margin-top: 0; font-size: 16px; }
.form { display: flex; flex-direction: column; gap: 12px; }
.form label { display: flex; flex-direction: column; gap: 4px; font-weight: 500; }
.form input, .form textarea, .form select, .add-form input, .add-form select {
  padding: 5px 7px; border: 1px solid #7f9db9; border-radius: 0;
  font-family: inherit; font-size: 14px;
}
.members { width: 100%; border-collapse: collapse; margin: 12px 0; }
.members th, .members td { padding: 8px 0; text-align: left; border-bottom: 1px solid var(--c-border); }
.add-form { display: flex; gap: 8px; align-items: center; margin-top: 12px; }
.add-form input { flex: 1; }
.danger-zone { border-color: #b00000; }
.btn.small { font-size: 12px; padding: 4px 8px; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.error { color: var(--c-danger); }
.muted { color: var(--c-text-muted); }
</style>
