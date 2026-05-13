export type Language = "r" | "julia" | "python";

export type ModelType = "sis" | "sir" | "seir" | "sirs" | "sidarthe" | "lstm";

export type SimulationStatus = "pending" | "running" | "completed" | "failed";

export interface User {
  id: string;
  email: string;
  is_super_admin: boolean;
  created_at: string;
}

export interface AuthResponse {
  token: string;
  expires_at: string;
  user_id: string;
  email: string;
  is_super_admin: boolean;
}

export type StudyRole = "admin" | "researcher" | "contributor" | "viewer";

export interface Study {
  id: string;
  name: string;
  disease_code: string;
  description?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface StudyMember {
  study_id: string;
  user_id: string;
  email?: string;
  role: StudyRole;
  joined_at: string;
}

export interface Membership {
  study: Study;
  role: StudyRole;
}

export interface MeResponse {
  id: string;
  email: string;
  is_super_admin: boolean;
  created_at: string;
  studies: Membership[] | null;
}

export interface Dataset {
  id: string;
  user_id: string;
  study_id: string;
  name: string;
  disease_code: string;
  uploaded_at: string;
  record_count: number;
}

export interface SimulationRun {
  id: string;
  user_id: string;
  study_id: string;
  dataset_id: string;
  model_type: ModelType;
  language: Language;
  parameters: Record<string, number>;
  population_n: number;
  t_max: number;
  status: SimulationStatus;
  error_message?: string;
  created_at: string;
  completed_at?: string;
}

export interface SimulationResultPoint {
  simulation_id: string;
  t: number;
  compartments: Record<string, number>;
}

export interface BenchmarkAggregate {
  model_type: ModelType;
  language: Language;
  run_count: number;
  median_wall_ms: number;
  p95_wall_ms: number;
  median_cpu_ms: number;
  median_memory_mb: number;
}

export interface CreateSimulationPayload {
  dataset_id: string;
  model_type: ModelType;
  language: Language;
  parameters: Record<string, number>;
  population_n?: number;
  t_max: number;
}
