<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRouter } from "vue-router";
import { useProfileStore } from "@/stores/profile.store";
import { useAuthStore } from "@/stores/auth.store";
import UserAvatar from "@/components/UserAvatar.vue";

const profile = useProfileStore();
const auth = useAuthStore();
const router = useRouter();

const fullName = ref("");
const affiliation = ref("");
const bio = ref("");
const saveMessage = ref<string | null>(null);
const avatarMessage = ref<string | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const uploading = ref(false);

const meId = computed(() => profile.myProfile?.id ?? auth.userId ?? "");

async function load() {
  await profile.fetchMyProfile();
  await profile.fetchCollaborators();
  if (profile.myProfile) {
    fullName.value = profile.myProfile.full_name;
    affiliation.value = profile.myProfile.affiliation;
    bio.value = profile.myProfile.bio;
  }
}

async function save() {
  saveMessage.value = null;
  try {
    await profile.updateMyProfile({
      full_name: fullName.value,
      affiliation: affiliation.value,
      bio: bio.value,
    });
    saveMessage.value = "Profil salvat.";
    setTimeout(() => (saveMessage.value = null), 2500);
  } catch (e) {
    saveMessage.value = (e as Error).message;
  }
}

async function onPickAvatar(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  avatarMessage.value = null;
  uploading.value = true;
  try {
    await profile.uploadMyAvatar(file);
    avatarMessage.value = "Avatar actualizat.";
    setTimeout(() => (avatarMessage.value = null), 2500);
  } catch (err) {
    avatarMessage.value = (err as Error).message;
  } finally {
    uploading.value = false;
    if (fileInput.value) fileInput.value.value = "";
  }
}

async function removeAvatar() {
  avatarMessage.value = null;
  try {
    await profile.deleteMyAvatar();
    avatarMessage.value = "Avatar eliminat.";
    setTimeout(() => (avatarMessage.value = null), 2500);
  } catch (err) {
    avatarMessage.value = (err as Error).message;
  }
}

function viewCollaborator(userId: string) {
  router.push({ name: "user-profile", params: { userId } });
}

onMounted(load);
</script>

<template>
  <div class="page">
    <h1>Profilul meu</h1>

    <section class="card">
      <h2>Detalii utilizator</h2>
      <div class="profile-grid">
        <div class="avatar-col">
          <UserAvatar
            v-if="meId"
            :user-id="meId"
            :email="profile.myProfile?.email"
            :full-name="profile.myProfile?.full_name"
            :has-avatar="profile.myProfile?.has_avatar"
            :size="128"
          />
          <div class="avatar-actions">
            <label class="btn">
              {{ uploading ? "Se încarcă..." : "Schimbă poza" }}
              <input
                ref="fileInput"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                @change="onPickAvatar"
                :disabled="uploading"
                hidden
              />
            </label>
            <button
              type="button"
              class="btn danger"
              v-if="profile.myProfile?.has_avatar"
              @click="removeAvatar"
            >
              Elimină
            </button>
          </div>
          <p class="hint" v-if="avatarMessage">{{ avatarMessage }}</p>
          <p class="hint">JPEG/PNG/WEBP, redimensionat automat la 256×256.</p>
        </div>

        <form class="form-col" @submit.prevent="save">
          <label>
            <span>Email</span>
            <input :value="profile.myProfile?.email" disabled />
          </label>

          <label>
            <span>Nume complet</span>
            <input
              v-model="fullName"
              maxlength="160"
              placeholder="ex: Tudor Geană"
            />
          </label>

          <label>
            <span>Afiliere / instituție</span>
            <input
              v-model="affiliation"
              maxlength="200"
              placeholder="ex: Universitatea Politehnica București — ETTI"
            />
          </label>

          <label>
            <span>Bio</span>
            <textarea
              v-model="bio"
              maxlength="1000"
              rows="5"
              placeholder="Câteva detalii despre tine, interese de cercetare, proiecte anterioare…"
            />
            <small class="char-count">{{ bio.length }} / 1000</small>
          </label>

          <div class="actions">
            <button type="submit" class="btn primary">Salvează</button>
            <span class="hint" v-if="saveMessage">{{ saveMessage }}</span>
          </div>
        </form>
      </div>
    </section>

    <section class="card">
      <h2>Colaboratori per studiu</h2>
      <p class="muted" v-if="profile.collaborators.length === 0">
        Încă nu împarți studii cu alți cercetători.
      </p>

      <div
        class="study-group"
        v-for="group in profile.collaborators"
        :key="group.study.id"
      >
        <header>
          <strong>{{ group.study.name }}</strong>
          <span class="badge">{{ group.study.disease_code }}</span>
          <span class="muted">Rolul meu: {{ group.my_role }}</span>
        </header>

        <ul class="members">
          <li
            v-for="m in group.members"
            :key="m.user_id + group.study.id"
            @click="viewCollaborator(m.user_id)"
            tabindex="0"
            @keydown.enter="viewCollaborator(m.user_id)"
          >
            <UserAvatar
              :user-id="m.user_id"
              :email="m.email"
              :full-name="m.full_name"
              :has-avatar="m.has_avatar"
              :size="40"
            />
            <div class="member-text">
              <div class="member-name">
                {{ m.full_name || m.email }}
                <span class="muted small" v-if="m.full_name">{{ m.email }}</span>
              </div>
              <div class="muted small" v-if="m.affiliation">{{ m.affiliation }}</div>
            </div>
            <span class="role-pill">{{ m.role }}</span>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page {
  max-width: 980px;
  margin: 0 auto;
  padding: 16px;
}

h1 {
  margin: 0 0 16px;
  font-size: 18px;
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
  margin: 0 0 12px;
  font-size: 14px;
  border-bottom: 1px solid var(--c-border);
  padding-bottom: 6px;
  color: var(--c-text-strong);
}

.profile-grid {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 20px;
}

@media (max-width: 720px) {
  .profile-grid { grid-template-columns: 1fr; }
}

.avatar-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.avatar-actions {
  display: flex;
  gap: 6px;
}

.form-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-col label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--c-text);
}

.form-col input,
.form-col textarea {
  font-size: 13px;
  padding: 5px 7px;
  border: 1px solid var(--input-border);
  background: var(--input-bg);
  color: var(--input-text);
}

.form-col textarea {
  resize: vertical;
  font-family: inherit;
}

.char-count {
  align-self: flex-end;
  color: var(--c-text-muted);
  font-size: 11px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn {
  display: inline-block;
  padding: 5px 12px;
  border: 1px solid var(--btn-border);
  background: linear-gradient(180deg, var(--btn-bg-1) 0%, var(--btn-bg-2) 48%, var(--btn-bg-3) 100%);
  box-shadow: inset 1px 1px 0 var(--btn-inset-light), inset -1px -1px 0 var(--btn-inset-dark);
  font-size: 12px;
  cursor: pointer;
  color: var(--btn-text);
  text-decoration: none;
}

.btn:hover {
  background: linear-gradient(180deg, var(--btn-hover-1) 0%, var(--btn-hover-2) 48%, var(--btn-hover-3) 100%);
}

.btn.primary {
  background: linear-gradient(180deg, var(--btn-primary-1) 0%, var(--btn-primary-2) 100%);
  color: #fff;
  font-weight: 700;
  border-color: var(--c-primary-deep);
}

.btn.danger {
  background: linear-gradient(180deg, var(--btn-danger-1) 0%, var(--btn-danger-3) 100%);
  color: #fff;
  border-color: var(--btn-danger-3);
}

.hint {
  font-size: 11px;
  color: var(--c-text-muted);
  margin: 0;
  text-align: center;
}

.muted { color: var(--c-text-muted); }
.muted.small { font-size: 11px; }

.badge {
  display: inline-block;
  background: var(--c-surface-soft);
  color: var(--c-text);
  border: 1px solid var(--c-border);
  padding: 1px 6px;
  font-size: 10px;
  margin: 0 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.role-pill {
  font-size: 10px;
  background: linear-gradient(180deg, var(--btn-bg-1) 0%, var(--btn-bg-3) 100%);
  color: var(--btn-text);
  border: 1px solid var(--c-border);
  padding: 1px 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.study-group {
  margin: 8px 0 14px;
}

.study-group header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding-bottom: 4px;
  margin-bottom: 4px;
  border-bottom: 1px dashed var(--c-border);
}

.members {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 6px;
}

.members li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px;
  border: 1px solid var(--c-border);
  background: var(--c-surface-soft);
  color: var(--c-text);
  cursor: pointer;
  transition: background var(--t-fast) var(--easing), border-color var(--t-fast) var(--easing);
}

.members li:hover {
  background: var(--table-row-hover);
  border-color: var(--c-primary);
}

.member-text {
  flex: 1;
  min-width: 0;
}

.member-name {
  font-size: 12px;
  font-weight: 700;
  display: flex;
  flex-direction: column;
  gap: 0;
}
</style>
