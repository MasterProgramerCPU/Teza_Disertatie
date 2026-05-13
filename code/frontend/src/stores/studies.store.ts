import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { api } from "@/api/client";
import type { Membership, Study, StudyMember, StudyRole } from "@/types";

const LS_CURRENT_STUDY = "emedicine.current_study_id";

export const useStudiesStore = defineStore("studies", () => {
  const memberships = ref<Membership[]>([]);
  const currentStudyId = ref<string | null>(localStorage.getItem(LS_CURRENT_STUDY));
  const loading = ref(false);
  const error = ref<string | null>(null);

  const currentMembership = computed<Membership | null>(() => {
    if (!currentStudyId.value) return null;
    return memberships.value.find((m) => m.study.id === currentStudyId.value) ?? null;
  });

  const currentStudy = computed<Study | null>(() => currentMembership.value?.study ?? null);
  const currentRole = computed<StudyRole | null>(() => currentMembership.value?.role ?? null);

  const canWriteDatasets = computed<boolean>(() => {
    const r = currentRole.value;
    return r === "admin" || r === "contributor";
  });
  const canWriteSimulations = computed<boolean>(() => {
    const r = currentRole.value;
    return r === "admin" || r === "researcher";
  });
  const canManageStudy = computed<boolean>(() => currentRole.value === "admin");

  function setMemberships(list: Membership[]) {
    memberships.value = list;
    // dacă studiul curent nu mai e valid, reset
    if (currentStudyId.value && !list.find((m) => m.study.id === currentStudyId.value)) {
      setCurrent(null);
    }
    // dacă nu există studiu curent dar avem unul singur, îl selectăm automat
    if (!currentStudyId.value && list.length === 1) {
      setCurrent(list[0].study.id);
    }
  }

  function setCurrent(id: string | null) {
    currentStudyId.value = id;
    if (id) localStorage.setItem(LS_CURRENT_STUDY, id);
    else localStorage.removeItem(LS_CURRENT_STUDY);
  }

  async function fetchMine() {
    loading.value = true;
    error.value = null;
    try {
      const list = await api.get<Membership[] | null>("/studies");
      setMemberships(list ?? []);
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  }

  async function create(name: string, diseaseCode: string, description: string): Promise<Study> {
    const study = await api.post<Study>("/studies", {
      name,
      disease_code: diseaseCode,
      description,
    });
    // refetch ca să avem și rolul (admin auto)
    await fetchMine();
    setCurrent(study.id);
    return study;
  }

  async function update(id: string, name: string, diseaseCode: string, description: string): Promise<Study> {
    const study = await api.patch<Study>(`/studies/${id}`, {
      name,
      disease_code: diseaseCode,
      description,
    });
    await fetchMine();
    return study;
  }

  async function remove(id: string) {
    await api.delete<unknown>(`/studies/${id}`);
    if (currentStudyId.value === id) setCurrent(null);
    await fetchMine();
  }

  // --- membri ---
  async function listMembers(studyId: string): Promise<StudyMember[]> {
    return (await api.get<StudyMember[] | null>(`/studies/${studyId}/members`)) ?? [];
  }

  async function addMember(studyId: string, email: string, role: StudyRole): Promise<StudyMember> {
    return await api.post<StudyMember>(`/studies/${studyId}/members`, { email, role });
  }

  async function updateMemberRole(studyId: string, userId: string, role: StudyRole) {
    await api.patch<unknown>(`/studies/${studyId}/members/${userId}`, { role });
  }

  async function removeMember(studyId: string, userId: string) {
    await api.delete<unknown>(`/studies/${studyId}/members/${userId}`);
  }

  return {
    memberships,
    currentStudyId,
    currentStudy,
    currentRole,
    currentMembership,
    canWriteDatasets,
    canWriteSimulations,
    canManageStudy,
    loading,
    error,
    fetchMine,
    setCurrent,
    create,
    update,
    remove,
    listMembers,
    addMember,
    updateMemberRole,
    removeMember,
  };
});
