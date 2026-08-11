import { describe, expect, it } from "vitest";

import { dailyComposeDisabled } from "./today-state";

describe("daily compose state", () => {
  it("stays enabled when no pending plan exists", () => {
    expect(
      dailyComposeDisabled({
        composePending: false,
        pendingPlanId: "",
        pendingPlanQueryPending: true,
      }),
    ).toBe(false);
  });

  it("waits while an existing pending plan is restored", () => {
    expect(
      dailyComposeDisabled({
        composePending: false,
        pendingPlanId: "019fe900-6000-7000-8000-000000000301",
        pendingPlanQueryPending: true,
      }),
    ).toBe(true);
  });
});
