export type Language = "r" | "julia" | "python";

export type SimulationStatus = "pending" | "running" | "completed" | "failed";

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  token: string;
  expires_at: string;
  user_id: string;
}

export interface Dataset {
  id: string;
  user_id: string;
  name: string;
  disease_code: string;
  uploaded_at: string;
  record_count: number;
}

export interface SimulationRun {
  id: string;
  user_id: string;
  dataset_id: string;
  language: Language;
  beta: number;
  gamma: number;
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
  s: number;
  i: number;
  r: number;
}

export interface BenchmarkAggregate {
  language: Language;
  run_count: number;
  median_wall_ms: number;
  p95_wall_ms: number;
  median_cpu_ms: number;
  median_memory_mb: number;
}

export interface CreateSimulationPayload {
  dataset_id: string;
  language: Language;
  beta: number;
  gamma: number;
  population_n?: number;
  t_max: number;
}
