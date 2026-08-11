import { describe, expect, it } from "vitest";

import { focusOptions } from "./practice-focus";

describe("free practice spaces", () => {
  it("covers every promised independent training space", () => {
    expect(focusOptions.map((option) => option.id)).toEqual([
      "grammar",
      "conjugation",
      "vocabulary",
      "spelling",
      "listening",
      "pronunciation",
      "translation",
      "writing",
    ]);
  });

  it("maps each space to executable primitives and modalities", () => {
    for (const option of focusOptions) {
      expect(option.primitives.length).toBeGreaterThanOrEqual(3);
      expect(option.modalities.length).toBeGreaterThan(0);
      expect(option.target).toBeTruthy();
    }
  });
});
