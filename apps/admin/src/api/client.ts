// Axios client; base URL resolved per request from persisted settings.
// Credentials (HTTP-only cookies) are sent automatically via withCredentials.
// Author: Al Amin Ahamed.
import axios from "axios";
import { getApiBase } from "@/lib/config";

export const apiClient = axios.create({
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config) => {
  config.baseURL = getApiBase();
  return config;
});
