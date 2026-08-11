import { createContext, useContext } from "react";

import type { ProfileResponse } from "../generated/model";

export interface ProfileContextValue {
  activeProfile: ProfileResponse | null;
  isPending: boolean;
  refresh: () => Promise<unknown>;
}

export const ProfileContext = createContext<ProfileContextValue | null>(null);

export function useActiveProfile(): ProfileContextValue {
  const value = useContext(ProfileContext);
  if (!value) {
    throw new Error("useActiveProfile must be used inside ProfileProvider");
  }
  return value;
}
