import { describe, expect, it } from "vitest";

import { selectActiveProfileId } from "./profile-selection";

const profiles = [
  { profile_id: "italian", status: "active" },
  { profile_id: "japanese", status: "foundations" },
  { profile_id: "archived", status: "archived" },
];

describe("selectActiveProfileId", () => {
  it("keeps the user's persisted profile", () => {
    expect(selectActiveProfileId(profiles, "japanese")).toBe("japanese");
  });

  it("falls back to the first trainable profile", () => {
    expect(selectActiveProfileId(profiles, "missing")).toBe("italian");
  });

  it("never activates an archived profile", () => {
    expect(selectActiveProfileId([{ profile_id: "archived", status: "archived" }], "archived"))
      .toBeNull();
  });
});
