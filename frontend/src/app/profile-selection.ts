interface SelectableProfile {
  profile_id: string;
  status: string;
}

const unavailableStatuses = new Set(["archived", "deleting", "deleted"]);

export function selectActiveProfileId(
  profiles: readonly SelectableProfile[],
  preferredProfileId: string | null,
): string | null {
  const trainable = profiles.filter(
    (profile) => !unavailableStatuses.has(profile.status),
  );
  if (
    preferredProfileId &&
    trainable.some((profile) => profile.profile_id === preferredProfileId)
  ) {
    return preferredProfileId;
  }
  return trainable[0]?.profile_id ?? null;
}
