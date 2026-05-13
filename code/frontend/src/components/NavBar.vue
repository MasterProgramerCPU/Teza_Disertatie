<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth.store";
import { useStudiesStore } from "@/stores/studies.store";

const auth = useAuthStore();
const studies = useStudiesStore();
const router = useRouter();

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

      <div class="study-selector" v-if="studies.memberships.length > 0">
        <select :value="studies.currentStudyId ?? '__choose__'" @change="onChangeStudy">
          <option value="__choose__" disabled>— alege studiu —</option>
          <option v-for="m in studies.memberships" :key="m.study.id" :value="m.study.id">
            {{ m.study.name }} ({{ m.role }})
          </option>
        </select>
        <router-link to="/studies" class="manage-link" title="Toate studiile">Studii</router-link>
      </div>

      <div class="links" v-if="studies.currentStudyId">
        <router-link to="/dashboard">Dashboard</router-link>
        <router-link to="/datasets">Seturi de date</router-link>
        <router-link to="/simulations/new" v-if="studies.canWriteSimulations">Simulare nouă</router-link>
        <router-link to="/compare">Comparare</router-link>
        <router-link to="/benchmarks">Benchmarks</router-link>
      </div>

      <div class="user">
        <span class="badge admin" v-if="auth.isSuperAdmin" title="Super administrator">SA</span>
        <span class="muted">{{ auth.email }}</span>
        <button @click="auth.logout">Logout</button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.navbar {
  background: linear-gradient(180deg, #2b72f2 0%, #0a46c4 46%, #07307f 100%);
  border-bottom: 1px solid #001b5d;
  box-shadow: inset 0 1px 0 #8bc2ff, 0 2px 0 rgba(0, 0, 0, 0.35);
}
.nav-inner {
  max-width: 1280px;
  margin: 0 auto;
  padding: 7px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand {
  font-weight: 700;
  color: #ffffff;
  text-decoration: none;
  font-size: 13px;
  text-shadow: 1px 1px 0 #00185f;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
}
.brand::before {
  content: "";
  width: 18px;
  height: 18px;
  display: inline-block;
  border: 1px solid #ffffff;
  background:
    linear-gradient(90deg, #f15132 0 50%, #58b947 50% 100%) top / 100% 50% no-repeat,
    linear-gradient(90deg, #2c7be5 0 50%, #f6d04d 50% 100%) bottom / 100% 50% no-repeat;
  box-shadow: 1px 1px 0 #00185f;
}
.study-selector {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  background: var(--c-surface);
  border: 1px solid #003c74;
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #858585;
}
.study-selector select {
  padding: 3px 6px;
  font-size: 12px;
  max-width: 260px;
}
.manage-link {
  text-decoration: none;
  font-size: 12px;
  color: #000080;
  padding: 2px 4px;
}
.manage-link:hover { color: #ff0000; }
.links {
  display: flex;
  gap: 4px;
  flex: 1;
  min-width: 0;
}
.links a {
  color: #000000;
  text-decoration: none;
  padding: 5px 10px;
  border: 1px solid #003c74;
  background: linear-gradient(180deg, #ffffff 0%, #ece9d8 48%, #d7d0bd 100%);
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #858585;
  font-size: 12px;
  white-space: nowrap;
}
.links a:hover { background: linear-gradient(180deg, #fffef7 0%, #f3edcc 48%, #ddd3a5 100%); color: #000000; }
.links a.router-link-active {
  background: linear-gradient(180deg, #245edb 0%, #0a46c4 100%);
  color: #ffffff;
  font-weight: 700;
  text-shadow: 1px 1px 0 #00185f;
  box-shadow: inset 1px 1px 0 #8bc2ff, inset -1px -1px 0 #001b5d;
}
.user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge.admin {
  background: linear-gradient(180deg, #ff7777 0%, #b00000 100%);
  color: #ffffff;
  padding: 2px 6px;
  border-radius: 0;
  border: 1px solid #7a0000;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.muted {
  color: #ffffff;
  font-size: 12px;
  text-shadow: 1px 1px 0 #00185f;
}

@media (max-width: 980px) {
  .nav-inner {
    align-items: stretch;
    flex-direction: column;
  }

  .links,
  .user {
    flex-wrap: wrap;
  }
}
</style>
