<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import NavBar from "@/components/NavBar.vue";

const route = useRoute();
const showNav = computed(() => route.name !== "login");
</script>

<template>
  <NavBar v-if="showNav" />
  <main class="container">
    <router-view />
  </main>
</template>

<style scoped>
.container {
  width: min(1220px, calc(100% - 28px));
  margin: 16px auto 0;
  padding: 14px;
  background: rgba(236, 233, 216, 0.96);
  border: 1px solid #0a246a;
  box-shadow: 4px 4px 0 rgba(0, 0, 0, 0.28);
}
</style>
