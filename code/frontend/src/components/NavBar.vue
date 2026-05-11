<script setup lang="ts">
import { useAuthStore } from "@/stores/auth.store";

const auth = useAuthStore();
</script>

<template>
  <nav class="navbar">
    <div class="nav-inner">
      <router-link to="/dashboard" class="brand">E-Medicine SIDARTH</router-link>
      <div class="links">
        <router-link to="/dashboard">Dashboard</router-link>
        <router-link to="/datasets">Seturi de date</router-link>
        <router-link to="/simulations/new">Simulare nouă</router-link>
        <router-link to="/compare">Comparare</router-link>
        <router-link to="/benchmarks">Benchmarks</router-link>
      </div>
      <div class="user">
        <span class="muted">{{ auth.email }}</span>
        <button @click="auth.logout">Logout</button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.navbar {
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  box-shadow: var(--shadow-sm);
}
.nav-inner {
  max-width: 1200px;
  margin: 0 auto;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.brand {
  font-weight: 700;
  color: var(--c-text);
  text-decoration: none;
  font-size: 16px;
}
.links {
  display: flex;
  gap: 16px;
  flex: 1;
}
.links a {
  color: var(--c-text-muted);
  text-decoration: none;
  padding: 6px 12px;
  border-radius: var(--radius);
}
.links a:hover {
  background: var(--c-bg);
  color: var(--c-text);
}
.links a.router-link-active {
  background: var(--c-bg);
  color: var(--c-primary);
  font-weight: 500;
}
.user {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
