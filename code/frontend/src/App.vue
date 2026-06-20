<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import NavBar from "@/components/NavBar.vue";
import { useTheme } from "@/composables/useTheme";

// Initializeaza tema la pornire (efectul aplica data-theme pe <html>).
useTheme();

const route = useRoute();
const showNav = computed(() => !["login", "register"].includes(route.name as string));
</script>

<template>
  <NavBar v-if="showNav" />
  <main class="container" :key="$route.fullPath">
    <router-view />
  </main>
</template>
