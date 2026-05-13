import axios, { AxiosError, type AxiosInstance, type AxiosResponse } from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

interface Envelope<T> {
  data?: T;
  error?: { code: number; message: string };
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

const tokenKey = "emedicine.token";

export function getToken(): string | null {
  return localStorage.getItem(tokenKey);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(tokenKey, token);
  else localStorage.removeItem(tokenKey);
}

const http: AxiosInstance = axios.create({ baseURL: BASE_URL });

http.interceptors.request.use((cfg) => {
  const token = getToken();
  if (token) {
    cfg.headers.Authorization = `Bearer ${token}`;
  }
  return cfg;
});

http.interceptors.response.use(
  (resp) => resp,
  (err: AxiosError<Envelope<unknown>>) => {
    if (err.response?.status === 401 && onUnauthorized) {
      onUnauthorized();
    }
    const payload = err.response?.data;
    const message = payload?.error?.message ?? err.message;
    return Promise.reject(new ApiError(err.response?.status ?? 0, message));
  },
);

async function unwrap<T>(promise: Promise<AxiosResponse<Envelope<T>>>): Promise<T> {
  const resp = await promise;
  if (resp.data?.error) {
    throw new ApiError(resp.status, resp.data.error.message);
  }
  return resp.data.data as T;
}

export const api = {
  get: <T>(url: string, params?: Record<string, unknown>) =>
    unwrap<T>(http.get(url, { params })),
  post: <T>(url: string, body?: unknown) => unwrap<T>(http.post(url, body)),
  patch: <T>(url: string, body?: unknown) => unwrap<T>(http.patch(url, body)),
  delete: <T>(url: string) => unwrap<T>(http.delete(url)),
  postForm: <T>(url: string, form: FormData) =>
    unwrap<T>(http.post(url, form, { headers: { "Content-Type": "multipart/form-data" } })),
  getBlob: async (url: string): Promise<Blob> => {
    const resp = await http.get(url, { responseType: "blob" });
    return resp.data as Blob;
  },
};
