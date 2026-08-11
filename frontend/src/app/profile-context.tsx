import type { ReactNode } from "react";

import { useListLanguageProfiles } from "../generated/polyglot";
import { queryFetch } from "../lib/api";
import { ProfileContext } from "./profile-state";

export function ProfileProvider({ children }: { children: ReactNode }) {
  const query = useListLanguageProfiles({
    fetch: queryFetch(),
    query: { retry: false },
  });
  const activeProfile =
    query.data?.status === 200
      ? (query.data.data.items.find((profile) => profile.status !== "archived") ?? null)
      : null;

  return (
    <ProfileContext.Provider
      value={{
        activeProfile,
        isPending: query.isPending,
        refresh: query.refetch,
      }}
    >
      {children}
    </ProfileContext.Provider>
  );
}
