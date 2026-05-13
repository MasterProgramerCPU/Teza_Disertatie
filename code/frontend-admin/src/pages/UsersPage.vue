<script setup lang="ts">
import { onMounted } from "vue";
import { useAdminStore } from "@/stores/admin.store";
import { useAuthStore } from "@/stores/auth.store";

const admin = useAdminStore();
const auth = useAuthStore();

onMounted(() => admin.fetchUsers());

async function toggle(userId: string, current: boolean) {
  if (!confirm(current ? "Revoci privilegiile de super admin?" : "Promovezi userul la super admin?")) return;
  try {
    await admin.setSuperAdmin(userId, !current);
  } catch (e) {
    alert((e as Error).message);
  }
}
</script>

<template>
  <h1>Utilizatori</h1>
  <p class="muted">{{ admin.users.length }} utilizatori înregistrați. Doar tu, ca super admin, poți promova/revoca privilegiile altora.</p>

  <p v-if="admin.loading">Se încarcă…</p>
  <p v-if="admin.error" class="error">{{ admin.error }}</p>

  <div class="card" v-if="admin.users.length > 0">
    <table>
      <thead>
        <tr>
          <th>Email</th>
          <th>Rol</th>
          <th>Înregistrat</th>
          <th>Acțiuni</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in admin.users" :key="u.id">
          <td>
            {{ u.email }}
            <span v-if="u.email === auth.email" class="muted">(tu)</span>
          </td>
          <td>
            <span v-if="u.is_super_admin" class="role-admin">Super Admin</span>
            <span v-else class="role-user">User</span>
          </td>
          <td class="muted">{{ new Date(u.created_at).toLocaleDateString("ro-RO") }}</td>
          <td>
            <button
              v-if="u.email !== auth.email"
              @click="toggle(u.id, u.is_super_admin)"
            >
              {{ u.is_super_admin ? "Revocă super admin" : "Promovează" }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.role-admin {
  background: #ffc9c9; color: #800000;
  padding: 2px 8px; border-radius: 0;
  border: 1px solid #b00000;
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.role-user {
  background: #ffffff; color: #4b4b4b;
  padding: 2px 8px; border-radius: 0;
  border: 1px solid #808080;
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
}
</style>
