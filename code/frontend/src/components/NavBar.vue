<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";
import { useStudiesStore } from "@/stores/studies.store";
import { useTheme } from "@/composables/useTheme";
import UserAvatar from "@/components/UserAvatar.vue";

const auth = useAuthStore();
const studies = useStudiesStore();
const router = useRouter();
const { theme, toggle: toggleTheme } = useTheme();

onMounted(async () => {
  if (auth.isAuthenticated && studies.memberships.length === 0) {
    await studies.fetchMine();
  }
});

function onChangeStudy(e: Event) {
  const id = (e.target as HTMLSelectElement).value;
  if (id === "__choose__") {
    router.push({ name: "studies" });
    return;
  }
  studies.setCurrent(id);
  // dacă suntem pe o pagină scoped pe study, forțăm reîncărcare
  router.go(0);
}
</script>

<template>
  <nav class="navbar">
    <div class="nav-inner">
      <router-link to="/dashboard" class="brand">E-Medicine SIR Workbench</router-link>

      <!-- Coloana din mijloc, 2 randuri: studiu selector sus, navigare jos -->
      <div class="middle">
        <div class="middle-row middle-top" v-if="studies.memberships.length > 0">
          <div class="study-selector">
            <span class="ss-lbl">Studiu:</span>
            <select :value="studies.currentStudyId ?? '__choose__'" @change="onChangeStudy">
              <option value="__choose__" disabled>— alege studiu —</option>
              <option v-for="m in studies.memberships" :key="m.study.id" :value="m.study.id">
                {{ m.study.name }} ({{ m.role }})
              </option>
            </select>
            <router-link to="/studies" class="manage-link" title="Toate studiile">Studii</router-link>
          </div>
        </div>
        <div class="middle-row middle-bottom" v-if="studies.currentStudyId">
          <router-link to="/dashboard">Dashboard</router-link>
          <router-link to="/datasets">Seturi de date</router-link>
          <router-link to="/simulations/new" v-if="studies.canWriteSimulations">Simulare nouă</router-link>
          <router-link to="/script-editor" v-if="studies.canWriteSimulations">Editor cod</router-link>
          <router-link to="/compare">Comparare</router-link>
          <router-link to="/benchmarks">Benchmarks</router-link>
          <router-link to="/map">Harta</router-link>
          <router-link
            to="/owner-dashboard"
            v-if="studies.canManageStudy"
            title="Panou administrator de studiu"
          >Panou admin</router-link>
        </div>
      </div>

      <router-link
        v-if="auth.userId"
        :to="{ name: 'profile' }"
        class="user-card"
        :title="`Profilul meu — ${auth.email ?? ''}`"
      >
        <UserAvatar :user-id="auth.userId" :email="auth.email ?? undefined" :size="36" />
        <div class="user-text">
          <div class="user-line-1">
            <span class="user-email" :title="auth.email ?? ''">{{ auth.email }}</span>
            <span class="badge admin" v-if="auth.isSuperAdmin" title="Super administrator">SA</span>
          </div>
          <div class="user-line-2">
            <span class="user-action">vezi profil</span>
            <span class="dot">·</span>
            <button
              type="button"
              class="logout-btn"
              @click.stop.prevent="auth.logout"
              title="Ieșire din cont"
            >Logout</button>
          </div>
        </div>
        <button
          type="button"
          class="theme-btn"
          @click.stop.prevent="toggleTheme"
          :title="theme === 'dark' ? 'Comută la temă luminoasă' : 'Comută la temă întunecată'"
          :aria-label="theme === 'dark' ? 'Temă luminoasă' : 'Temă întunecată'"
        >
          <span class="theme-icon">{{ theme === 'dark' ? '☀' : '☾' }}</span>
        </button>
      </router-link>
    </div>
  </nav>
</template>

<style scoped>
.navbar {
  background: linear-gradient(180deg, var(--c-taskbar-1) 0%, var(--c-primary) 46%, var(--c-taskbar-3) 100%);
  border-bottom: 1px solid var(--c-border-deep);
  box-shadow: inset 0 1px 0 var(--c-taskbar-highlight), 0 2px 0 rgba(0, 0, 0, 0.35);
  transition: background var(--t-med) var(--easing);
}

.nav-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: 8px 14px;
  display: flex;
  align-items: center;
  gap: 14px;
}

/* --- Brand --- */
.brand {
  font-weight: 700;
  color: #ffffff;
  text-decoration: none;
  font-size: 14px;
  text-shadow: 1px 1px 0 #00185f;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  flex-shrink: 0;
}
.brand::before {
  content: "";
  width: 20px;
  height: 20px;
  display: inline-block;
  border: 1px solid #ffffff;
  background:
    linear-gradient(90deg, #f15132 0 50%, #58b947 50% 100%) top / 100% 50% no-repeat,
    linear-gradient(90deg, #2c7be5 0 50%, #f6d04d 50% 100%) bottom / 100% 50% no-repeat;
  box-shadow: 1px 1px 0 #00185f;
}

/* --- Coloana mijlocie pe 2 randuri --- */
.middle {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.middle-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 28px;
}
.middle-bottom {
  gap: 4px;
  row-gap: 4px;
}

/* --- Selector studiu --- */
.study-selector {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  background: var(--c-surface);
  color: var(--c-text);
  border: 1px solid var(--btn-border);
  box-shadow: inset 1px 1px 0 var(--btn-inset-light), inset -1px -1px 0 var(--btn-inset-dark);
  max-width: 520px;
  flex: 1 1 320px;
  min-width: 220px;
  transition: background var(--t-med) var(--easing);
}
.ss-lbl {
  font-size: 11px;
  color: var(--c-primary-deep);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
[data-theme="dark"] .ss-lbl { color: var(--c-link); }

.study-selector select {
  padding: 3px 6px;
  font-size: 12px;
  flex: 1;
  min-width: 0;
}
.manage-link {
  text-decoration: none;
  font-size: 12px;
  color: var(--c-link);
  padding: 2px 6px;
  border-left: 1px solid var(--c-border);
  transition: color var(--t-fast) var(--easing);
}
.manage-link:hover { color: var(--c-link-hover); }

/* --- Linkuri navigare (rand 2 al coloanei mijlocii) --- */
.middle-bottom a {
  color: var(--btn-text);
  text-decoration: none;
  padding: 4px 10px;
  border: 1px solid var(--btn-border);
  background: linear-gradient(180deg, var(--btn-bg-1) 0%, var(--btn-bg-2) 48%, var(--btn-bg-3) 100%);
  box-shadow: inset 1px 1px 0 var(--btn-inset-light), inset -1px -1px 0 var(--btn-inset-dark);
  font-size: 12px;
  white-space: nowrap;
  transition:
    background var(--t-fast) var(--easing),
    transform var(--t-fast) var(--easing),
    color var(--t-fast) var(--easing);
}
.middle-bottom a:hover {
  background: linear-gradient(180deg, var(--btn-hover-1) 0%, var(--btn-hover-2) 48%, var(--btn-hover-3) 100%);
  color: var(--btn-text);
  transform: translateY(-1px);
}
.middle-bottom a:active {
  transform: translateY(0);
  box-shadow: inset 1px 1px 0 var(--btn-inset-dark), inset -1px -1px 0 var(--btn-inset-light);
}
.middle-bottom a.router-link-active {
  background: linear-gradient(180deg, var(--btn-primary-1) 0%, var(--btn-primary-2) 100%);
  color: #ffffff;
  font-weight: 700;
  text-shadow: 1px 1px 0 var(--c-primary-deep);
  box-shadow: inset 1px 1px 0 var(--c-taskbar-highlight), inset -1px -1px 0 var(--c-primary-deep);
}

/* --- Card cont (2 randuri) --- */
.user-card {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.10);
  border: 1px solid rgba(255, 255, 255, 0.28);
  text-decoration: none;
  flex-shrink: 0;
  margin-left: auto;
}
.user-card:hover {
  background: rgba(255, 255, 255, 0.20);
  border-color: rgba(255, 255, 255, 0.55);
}
.user-text {
  display: flex;
  flex-direction: column;
  gap: 0;
  line-height: 1.2;
  min-width: 0;
}
.user-line-1 {
  display: flex;
  align-items: center;
  gap: 6px;
}
.user-line-2 {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.85);
  text-shadow: 1px 1px 0 #00185f;
}
.user-email {
  color: #ffffff;
  font-size: 12px;
  font-weight: 700;
  text-shadow: 1px 1px 0 #00185f;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-action {
  color: rgba(255, 255, 255, 0.85);
  text-transform: lowercase;
}
.dot { color: rgba(255, 255, 255, 0.55); }
.badge.admin {
  background: linear-gradient(180deg, #ff7777 0%, #b00000 100%);
  color: #ffffff;
  padding: 1px 5px;
  border-radius: 0;
  border: 1px solid #7a0000;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.5px;
  flex-shrink: 0;
}
.logout-btn {
  background: none;
  border: none;
  color: #ffd6a8;
  padding: 0;
  font-size: 10px;
  cursor: pointer;
  text-decoration: underline;
  font-family: inherit;
  transition: color var(--t-fast) var(--easing);
}
.logout-btn:hover { color: #ff7777; }

/* Buton de schimbare temă: doar icon, pătrățel 28x28 cu bevel Win98 */
.theme-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-left: 4px;
  padding: 0;
  border: 1px solid var(--c-border-deep);
  background: linear-gradient(180deg, var(--btn-bg-1) 0%, var(--btn-bg-2) 48%, var(--btn-bg-3) 100%);
  box-shadow: inset 1px 1px 0 var(--btn-inset-light), inset -1px -1px 0 var(--btn-inset-dark);
  cursor: pointer;
  color: var(--c-text-strong);
  font-family: inherit;
  transition:
    background var(--t-fast) var(--easing),
    transform var(--t-fast) var(--easing),
    box-shadow var(--t-fast) var(--easing);
}
.theme-btn:hover {
  background: linear-gradient(180deg, var(--btn-hover-1) 0%, var(--btn-hover-2) 48%, var(--btn-hover-3) 100%);
  transform: translateY(-1px);
}
.theme-btn:active {
  transform: translateY(0);
  box-shadow: inset 1px 1px 0 var(--btn-inset-dark), inset -1px -1px 0 var(--btn-inset-light);
}
.theme-icon {
  font-size: 16px;
  line-height: 1;
  display: inline-block;
}

@media (max-width: 720px) {
  .nav-inner { flex-wrap: wrap; }
  .study-selector { flex-basis: 100%; max-width: none; }
  .user-card { margin-left: 0; margin-top: 4px; }
}
</style>
