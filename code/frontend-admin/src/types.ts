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
