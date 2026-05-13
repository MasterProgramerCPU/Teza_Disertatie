<script setup lang="ts">
import { useAuthStore } from "@/stores/auth.store";

const auth = useAuthStore();
</script>

<template>
  <nav class="navbar">
    <div class="nav-inner">
      <router-link to="/dashboard" class="brand">
        <span class="badge">SA</span>
        E-Medicine Admin Console
      </router-link>
      <div class="links">
        <router-link to="/dashboard">Dashboard</router-link>
        <router-link to="/users">Utilizatori</router-link>
        <router-link to="/studies">Studii</router-link>
      </div>
      <div class="user">
        <a href="http://sir-workbench.ro" class="back" title="Înapoi la aplicația principală">↩ Aplicație</a>
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
  display: flex;
  align-items: center;
  gap: 8px;
  text-shadow: 1px 1px 0 #00185f;
  white-space: nowrap;
}
.badge {
  background: linear-gradient(180deg, #ff7777 0%, #b00000 100%);
  color: #ffffff;
  padding: 2px 6px;
  border-radius: 0;
  border: 1px solid #7a0000;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.links {
  display: flex;
  gap: 4px;
  flex: 1;
  margin-left: 12px;
}
.links a {
  color: #000000;
  text-decoration: none;
  padding: 5px 10px;
  border: 1px solid #003c74;
  background: linear-gradient(180deg, #ffffff 0%, #ece9d8 48%, #d7d0bd 100%);
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #858585;
  white-space: nowrap;
}
.links a:hover { background: linear-gradient(180deg, #fffef7 0%, #f3edcc 48%, #ddd3a5 100%); color: #000000; }
.links a.router-link-active {
  background: linear-gradient(180deg, #b00000 0%, #7a0000 100%);
  color: #ffffff;
  font-weight: 700;
  text-shadow: 1px 1px 0 #300000;
  box-shadow: inset 1px 1px 0 #ffc5c5, inset -1px -1px 0 #540000;
}
.user {
  display: flex;
  align-items: center;
  gap: 8px;
}
.back { color: #ffffff; text-decoration: underline; font-size: 12px; text-shadow: 1px 1px 0 #00185f; }
.back:hover { color: #ffffcc; }
.muted { color: #ffffff; font-size: 12px; text-shadow: 1px 1px 0 #00185f; }

@media (max-width: 900px) {
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
