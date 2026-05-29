// Admin connection + theme settings, persisted in localStorage.
// Author: Al Amin Ahamed.

const API_BASE_KEY = "wprag_api_base";
const TOKEN_KEY = "wprag_admin_token";
const THEME_KEY = "wprag_theme";

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

export type Theme = "light" | "dark";

export function getTheme(): Theme {
  return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
}
export function setTheme(theme: Theme): void {
  localStorage.setItem(THEME_KEY, theme);
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function applyStoredTheme(): void {
  document.documentElement.classList.toggle("dark", getTheme() === "dark");
}
