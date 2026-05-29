// Reactive admin profile (updates on save / cross-tab). Author: Al Amin Ahamed.
import { useEffect, useState } from "react";
import { getProfile, PROFILE_EVENT, type Profile } from "@/lib/profile";

export function useProfile(): Profile {
  const [profile, setProfileState] = useState<Profile>(getProfile);
  useEffect(() => {
    const refresh = () => setProfileState(getProfile());
    window.addEventListener(PROFILE_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(PROFILE_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);
  return profile;
}
