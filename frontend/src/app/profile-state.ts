import { createContext, useContext } from "react";

import type { LanguagePackResponse, ProfileResponse } from "../generated/model";

export interface ProfileContextValue {
  activeProfile: ProfileResponse | null;
  activePack: LanguagePackResponse | null;
  packs: readonly LanguagePackResponse[];
  profiles: readonly ProfileResponse[];
  isPending: boolean;
  refresh: () => Promise<unknown>;
  selectProfile: (profileId: string) => void;
}

export const ProfileContext = createContext<ProfileContextValue | null>(null);

export function useActiveProfile(): ProfileContextValue {
  const value = useContext(ProfileContext);
  if (!value) {
    throw new Error("useActiveProfile must be used inside ProfileProvider");
  }
  return value;
}
