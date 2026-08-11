import { describe, expect, it } from "vitest";

import {
  activeRunStorageKey,
  freePracticeRunStorageKey,
  pendingDailyPlanStorageKey,
} from "./browser-storage";

describe("activeRunStorageKey", () => {
  it("isolates an active run by account and language profile", () => {
    expect(activeRunStorageKey("account-a", "profile-it")).toBe(
      "polyglot.active-run.account-a.profile-it",
    );
    expect(activeRunStorageKey("account-b", "profile-it")).not.toBe(
      activeRunStorageKey("account-a", "profile-it"),
    );
  });

  it("isolates a pending plan by account, profile and day", () => {
    expect(pendingDailyPlanStorageKey("account-a", "profile-it", "2026-08-11")).toBe(
      "polyglot.pending-daily-plan.account-a.profile-it.2026-08-11",
    );
    expect(
      pendingDailyPlanStorageKey("account-a", "profile-it", "2026-08-12"),
    ).not.toBe(
      pendingDailyPlanStorageKey("account-a", "profile-it", "2026-08-11"),
    );
  });
});

describe("freePracticeRunStorageKey", () => {
  it("does not collide with the daily sprint for the same profile", () => {
    expect(freePracticeRunStorageKey("account-a", "profile-it")).not.toBe(
      activeRunStorageKey("account-a", "profile-it"),
    );
  });
});
