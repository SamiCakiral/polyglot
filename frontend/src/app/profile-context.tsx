import { type ReactNode, useState } from "react";

import { useListLanguagePacks, useListLanguageProfiles } from "../generated/polyglot";
import { queryFetch } from "../lib/api";
import { selectActiveProfileId } from "./profile-selection";
import { ProfileContext } from "./profile-state";

const ACTIVE_PROFILE_KEY = "polyglot.active-profile";

export function ProfileProvider({ children }: { children: ReactNode }) {
  const query = useListLanguageProfiles({
    fetch: queryFetch(),
    query: { retry: false },
  });
  const packsQuery = useListLanguagePacks(
    { limit: 100 },
    { fetch: queryFetch(), query: { retry: false } },
  );
  const [preferredProfileId, setPreferredProfileId] = useState<string | null>(
    () => localStorage.getItem(ACTIVE_PROFILE_KEY),
  );
  const profiles = query.data?.status === 200 ? query.data.data.items : [];
  const activeProfileId = selectActiveProfileId(profiles, preferredProfileId);
  const activeProfile =
    profiles.find((profile) => profile.profile_id === activeProfileId) ?? null;
  const packs = packsQuery.data?.status === 200 ? packsQuery.data.data.items : [];
  const activePack =
    packs.find(
      (pack) => pack.target_variety_id === activeProfile?.target_variety_id,
    ) ?? null;

  function selectProfile(profileId: string) {
    if (!profiles.some((profile) => profile.profile_id === profileId)) return;
    localStorage.setItem(ACTIVE_PROFILE_KEY, profileId);
    setPreferredProfileId(profileId);
  }

  return (
    <ProfileContext.Provider
      value={{
        activeProfile,
        activePack,
        packs,
        profiles,
        isPending: query.isPending || packsQuery.isPending,
        refresh: query.refetch,
        selectProfile,
      }}
    >
      {children}
    </ProfileContext.Provider>
  );
}
