import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "@/api/client";
import type {
  UserProfile,
  UserProfileUpdate,
  CollaboratorsByStudy,
} from "@/types";

// Cache de blob URL-uri pentru avatare: cheia e userId, valoarea e blob: URL.
// Url-urile blob sunt revocate cand reincarcam (uploadMyAvatar / refreshAvatar).
const avatarCache = new Map<string, string>();

function revokeAvatar(userId: string) {
  const prev = avatarCache.get(userId);
  if (prev) {
    URL.revokeObjectURL(prev);
    avatarCache.delete(userId);
  }
}

export const useProfileStore = defineStore("profile", () => {
  const myProfile = ref<UserProfile | null>(null);
  const collaborators = ref<CollaboratorsByStudy[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchMyProfile() {
    loading.value = true;
    error.value = null;
    try {
      myProfile.value = await api.get<UserProfile>("/me/profile");
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function fetchCollaborators() {
    try {
      const data = await api.get<CollaboratorsByStudy[] | null>(
        "/me/collaborators",
      );
      collaborators.value = data ?? [];
    } catch (e) {
      error.value = (e as Error).message;
    }
  }

  async function updateMyProfile(patch: UserProfileUpdate) {
    loading.value = true;
    error.value = null;
    try {
      myProfile.value = await api.patch<UserProfile>("/me/profile", patch);
    } catch (e) {
      error.value = (e as Error).message;
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function uploadMyAvatar(file: File): Promise<void> {
    error.value = null;
    const { dataBase64, mimeType } = await resizeAvatar(file);
    await api.put<{ has_avatar: boolean }>("/me/avatar", {
      data_base64: dataBase64,
      mime_type: mimeType,
    });
    if (myProfile.value) {
      myProfile.value.has_avatar = true;
      revokeAvatar(myProfile.value.id);
    }
  }

  async function deleteMyAvatar(): Promise<void> {
    await api.delete<{ has_avatar: boolean }>("/me/avatar");
    if (myProfile.value) {
      myProfile.value.has_avatar = false;
      revokeAvatar(myProfile.value.id);
    }
  }

  async function fetchUserProfile(userId: string): Promise<UserProfile> {
    return await api.get<UserProfile>(`/users/${userId}/profile`);
  }

  /**
   * Returneaza un blob: URL pentru avatarul utilizatorului, descarcand-l
   * autentificat prin Axios (cu header-ul Authorization atasat).
   * URL-urile sunt cache-uite per userId; cache-ul e invalidat la
   * upload/delete propriu sau cu refreshAvatar().
   */
  async function getAvatarUrl(userId: string): Promise<string | null> {
    const cached = avatarCache.get(userId);
    if (cached) return cached;
    try {
      const blob = await api.getBlob(`/users/${userId}/avatar`);
      const url = URL.createObjectURL(blob);
      avatarCache.set(userId, url);
      return url;
    } catch {
      return null;
    }
  }

  function refreshAvatar(userId: string) {
    revokeAvatar(userId);
  }

  return {
    myProfile,
    collaborators,
    loading,
    error,
    fetchMyProfile,
    fetchCollaborators,
    updateMyProfile,
    uploadMyAvatar,
    deleteMyAvatar,
    fetchUserProfile,
    getAvatarUrl,
    refreshAvatar,
  };
});

// Resize si compress imaginea pana incape sub limita de 256KB,
// pentru ca backend-ul refuza payload-uri mai mari.
async function resizeAvatar(file: File): Promise<{ dataBase64: string; mimeType: string }> {
  const maxBytes = 256 * 1024;
  const targetSide = 256; // 256x256 e suficient pentru un avatar
  const img = await loadImage(file);

  const canvas = document.createElement("canvas");
  // Decupare patrata din centru
  const side = Math.min(img.width, img.height);
  const sx = (img.width - side) / 2;
  const sy = (img.height - side) / 2;
  canvas.width = targetSide;
  canvas.height = targetSide;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas indisponibil");
  ctx.drawImage(img, sx, sy, side, side, 0, 0, targetSide, targetSide);

  // JPEG cu calitate descrescatoare pana cand binarul intra sub limita.
  for (const q of [0.85, 0.75, 0.65, 0.55, 0.45]) {
    const blob = await canvasToBlob(canvas, "image/jpeg", q);
    if (blob.size <= maxBytes) {
      return { dataBase64: await blobToBase64(blob), mimeType: "image/jpeg" };
    }
  }
  // Ultim retry la calitate joasa; chiar daca ramane peste, lasam serverul sa decida.
  const fallback = await canvasToBlob(canvas, "image/jpeg", 0.4);
  return { dataBase64: await blobToBase64(fallback), mimeType: "image/jpeg" };
}

function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = (e) => {
      URL.revokeObjectURL(url);
      reject(e);
    };
    img.src = url;
  });
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob) reject(new Error("blob conversion failed"));
        else resolve(blob);
      },
      type,
      quality,
    );
  });
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // dataURL: "data:image/jpeg;base64,...." -> luam doar partea de dupa virgula
      const idx = result.indexOf(",");
      resolve(idx >= 0 ? result.slice(idx + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
