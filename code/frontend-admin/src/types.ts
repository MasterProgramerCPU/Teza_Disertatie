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

export interface Study {
  id: string;
  name: string;
  disease_code: string;
  description?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AdminStats {
  users: number;
  super_admins: number;
  studies: number;
  datasets: number;
  epi_records: number;
  simulations: number;
  simulations_completed: number;
  benchmarks: number;
}

export interface LabeledCount {
  label: string;
  count: number;
}

export interface StudyVolume {
  study_id: string;
  name: string;
  record_count: number;
}

export interface Breakdown {
  simulations_by_status: LabeledCount[];
  simulations_by_model: LabeledCount[];
  simulations_by_language: LabeledCount[];
  datasets_by_disease: LabeledCount[];
  studies_by_disease: LabeledCount[];
  top_studies_by_records: StudyVolume[];
}

export interface RecentSimulation {
  id: string;
  study_id: string;
  study_name: string;
  user_email: string;
  model_type: string;
  language: string;
  status: string;
  t_max: number;
  created_at: string;
  completed_at?: string;
}

export interface RecentDataset {
  id: string;
  study_id: string;
  study_name: string;
  user_email: string;
  name: string;
  disease_code: string;
  record_count: number;
  uploaded_at: string;
}

// Folosite pe pagina de detaliu a unui studiu (super-admin reuseaza endpoint-urile
// /studies/{id}/* obisnuite, gratie bypass-ului din middleware-ul RBAC).
export interface StudyMember {
  study_id: string;
  user_id: string;
  email?: string;
  role: string;
  joined_at: string;
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

export interface Simulation {
  id: string;
  user_id: string;
  study_id: string;
  dataset_id: string;
  model_type: string;
  language: string;
  parameters: Record<string, number>;
  population_n: number;
  t_max: number;
  status: string;
  error_message?: string;
  created_at: string;
  completed_at?: string;
}

export interface BenchmarkAggregate {
  model_type: string;
  language: string;
  run_count: number;
  median_wall_ms: number;
  p95_wall_ms: number;
  median_cpu_ms: number;
  median_memory_mb: number;
}
