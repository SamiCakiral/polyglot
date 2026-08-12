export function placementRunKey(profileId: string): string {
  return `polyglot.placement-run.${profileId}`;
}

export function rememberPlacementRun(profileId: string, runId: string): void {
  localStorage.setItem(placementRunKey(profileId), runId);
}

export function forgetPlacementRun(profileId: string): void {
  localStorage.removeItem(placementRunKey(profileId));
}
