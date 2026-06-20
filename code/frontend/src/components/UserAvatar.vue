<script setup lang="ts">
import { ref, watch, computed, onMounted } from "vue";
import { useProfileStore } from "@/stores/profile.store";

const props = defineProps<{
  userId: string;
  email?: string;
  fullName?: string;
  hasAvatar?: boolean;
  size?: number;
}>();

const profile = useProfileStore();
const url = ref<string | null>(null);

const side = computed(() => props.size ?? 32);

const initials = computed(() => {
  const src = (props.fullName || props.email || "?").trim();
  const parts = src.split(/[\s@._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
});

// Culoare derivata din userId pentru placeholder colorat consistent.
const placeholderBg = computed(() => {
  const id = props.userId || "x";
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) & 0xfffffff;
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 45%, 45%)`;
});

async function load() {
  if (!props.userId) return;
  if (props.hasAvatar === false) {
    url.value = null;
    return;
  }
  url.value = await profile.getAvatarUrl(props.userId);
}

onMounted(load);
watch(() => [props.userId, props.hasAvatar], load);
</script>

<template>
  <span class="avatar" :style="{ width: side + 'px', height: side + 'px' }">
    <img v-if="url" :src="url" :alt="email ?? fullName ?? userId" />
    <span v-else class="placeholder" :style="{ background: placeholderBg, fontSize: Math.round(side * 0.4) + 'px' }">
      {{ initials }}
    </span>
  </span>
</template>

<style scoped>
.avatar {
  display: inline-block;
  border: 1px solid #003c74;
  background: #ccc;
  overflow: hidden;
  vertical-align: middle;
  box-shadow: inset 1px 1px 0 #ffffff, inset -1px -1px 0 #858585;
}
.avatar img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}
.placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-weight: 700;
  text-shadow: 1px 1px 0 rgba(0, 0, 0, 0.4);
  letter-spacing: 0.5px;
}
</style>
