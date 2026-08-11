export function dailyComposeDisabled({
  composePending,
  pendingPlanId,
  pendingPlanQueryPending,
}: {
  composePending: boolean;
  pendingPlanId: string;
  pendingPlanQueryPending: boolean;
}): boolean {
  return (
    composePending ||
    (Boolean(pendingPlanId) && pendingPlanQueryPending)
  );
}
