// Admin connection settings, persisted in localStorage.
// Author: Al Amin Ahamed.

const API_BASE_KEY = "wprag_api_base";
const TOKEN_KEY = "wprag_admin_token";

const DEFAULT_API_BASE =
  (import.meta.env as Record<string, string | undefined>)["VITE_API_BASE_URL"] ??
  "http://localhost:8000";

export function getApiBase(): string {
  return localStorage.getItem(API_BASE_KEY) ?? DEFAULT_API_BASE;
}

export function setApiBase(value: string): void {
  localStorage.setItem(API_BASE_KEY, value);
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(value: string): void {
  localStorage.setItem(TOKEN_KEY, value);
}
