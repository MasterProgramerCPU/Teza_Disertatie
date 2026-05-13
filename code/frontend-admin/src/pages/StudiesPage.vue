<script setup lang="ts">
import { onMounted } from "vue";
import { useAdminStore } from "@/stores/admin.store";

const admin = useAdminStore();

onMounted(() => admin.fetchStudies());
</script>

<template>
  <h1>Studii (vedere globală)</h1>
  <p class="muted">{{ admin.studies.length }} studii înregistrate. Lista completă, indiferent de membership.</p>

  <p v-if="admin.loading">Se încarcă…</p>
  <p v-if="admin.error" class="error">{{ admin.error }}</p>

  <div class="card" v-if="admin.studies.length > 0">
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
        <tr v-for="s in admin.studies" :key="s.id">
          <td><strong>{{ s.name }}</strong></td>
          <td><code>{{ s.disease_code }}</code></td>
          <td class="muted">{{ s.description || "—" }}</td>
          <td class="muted">{{ new Date(s.created_at).toLocaleDateString("ro-RO") }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
