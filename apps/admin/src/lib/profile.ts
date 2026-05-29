// Admin operator profile (name + email), persisted in localStorage, plus the
// Gravatar URL derived from the email. Author: Al Amin Ahamed.
import { md5 } from "./md5";

const NAME_KEY = "wprag_profile_name";
const EMAIL_KEY = "wprag_profile_email";

const DEFAULT_NAME = "Al Amin Ahamed";
const DEFAULT_EMAIL = "mrabir.ahamed@gmail.com";

export interface Profile {
  name: string;
  email: string;
}

export function getProfile(): Profile {
  return {
    name: localStorage.getItem(NAME_KEY) ?? DEFAULT_NAME,
    email: localStorage.getItem(EMAIL_KEY) ?? DEFAULT_EMAIL,
  };
}

export const PROFILE_EVENT = "wprag:profile";

export function setProfile(profile: Profile): void {
  localStorage.setItem(NAME_KEY, profile.name);
  localStorage.setItem(EMAIL_KEY, profile.email);
  window.dispatchEvent(new Event(PROFILE_EVENT));
}

/** Gravatar avatar URL for an email (identicon fallback). */
export function gravatarUrl(email: string, size = 64): string {
  const hash = md5(email.trim().toLowerCase());
  return `https://www.gravatar.com/avatar/${hash}?d=identicon&s=${size}`;
}

/** Up-to-two-letter initials for an avatar fallback. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0] ?? "";
  if (parts.length === 0) return "?";
  if (parts.length === 1) return first.slice(0, 2).toUpperCase();
  const last = parts[parts.length - 1] ?? "";
  return ((first[0] ?? "") + (last[0] ?? "")).toUpperCase();
}
