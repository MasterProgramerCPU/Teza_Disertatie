<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useAdminStore } from "@/stores/admin.store";

const admin = useAdminStore();
const filter = ref("");

onMounted(() => admin.fetchStudies());

const filtered = computed(() => {
  const q = filter.value.trim().toLowerCase();
  if (!q) return admin.studies;
  return admin.studies.filter((s) =>
    s.name.toLowerCase().includes(q) ||
    s.disease_code.toLowerCase().includes(q) ||
    (s.description ?? "").toLowerCase().includes(q),
  );
});
</script>

<template>
  <h1>Studii (vedere globală)</h1>
  <p class="muted">
    {{ admin.studies.length }} studii înregistrate.
    Click pe un studiu pentru detalii (membri, seturi de date, simulări, benchmarks).
  </p>

  <p v-if="admin.loading">Se încarcă…</p>
  <p v-if="admin.error" class="error">{{ admin.error }}</p>

  <div class="filter-bar" v-if="admin.studies.length > 0">
    <input v-model="filter" type="search" placeholder="Filtrează după nume, boală sau descriere…" />
    <span class="muted">{{ filtered.length }} / {{ admin.studies.length }}</span>
  </div>

  <div class="card" v-if="filtered.length > 0">
    <table>
      <thead>
        <tr>
          <th>Nume</th>
          <th>Cod boală</th>
          <th>Descriere</th>
          <th>Creat</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in filtered" :key="s.id" class="clickable">
          <td>
            <router-link :to="`/studies/${s.id}`">
              <strong>{{ s.name }}</strong>
            </router-link>
          </td>
          <td><code>{{ s.disease_code }}</code></td>
          <td class="muted desc">{{ s.description || "—" }}</td>
          <td class="muted nowrap">{{ new Date(s.created_at).toLocaleDateString("ro-RO") }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p v-else-if="admin.studies.length > 0 && filter" class="muted">
    Niciun studiu nu se potrivește filtrului „{{ filter }}".
  </p>
</template>

<style scoped>
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0;
}
.filter-bar input {
  flex: 1;
  max-width: 480px;
}
.desc {
  max-width: 520px;
}
.nowrap {
  white-space: nowrap;
}
.clickable td a {
  text-decoration: none;
  color: var(--c-accent);
}
.clickable td a:hover {
  text-decoration: underline;
  color: #ff0000;
}
</style>
