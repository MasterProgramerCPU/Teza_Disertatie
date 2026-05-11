<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import NavBar from "@/components/NavBar.vue";

const route = useRoute();
const showNav = computed(() => !["login", "register"].includes(route.name as string));
</script>

<template>
  <NavBar v-if="showNav" />
  <main class="container">
    <router-view />
  </main>
</template>
