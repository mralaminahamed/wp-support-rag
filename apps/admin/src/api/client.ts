// Axios client; base URL and bearer token are resolved per request from the
// persisted admin settings (apps/admin/src/lib/config.ts).
// Author: Al Amin Ahamed.
import axios from "axios";
import { getApiBase, getToken } from "@/lib/config";

export const apiClient = axios.create({
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config) => {
  config.baseURL = getApiBase();
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
