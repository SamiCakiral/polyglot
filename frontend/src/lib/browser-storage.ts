export function activeRunStorageKey(accountId: string, profileId: string) {
  return `polyglot.active-run.${accountId}.${profileId}`;
}

export function freePracticeRunStorageKey(accountId: string, profileId: string) {
  return `polyglot.free-practice-run.${accountId}.${profileId}`;
}

export function pendingDailyPlanStorageKey(
  accountId: string,
  profileId: string,
  pedagogicalDay: string,
) {
  return `polyglot.pending-daily-plan.${accountId}.${profileId}.${pedagogicalDay}`;
}
