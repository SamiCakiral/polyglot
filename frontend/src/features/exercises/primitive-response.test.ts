import { describe, expect, it } from "vitest";

import {
  emptyResponse,
  isResponseComplete,
  normalizeResponse,
} from "./primitive-response";

describe("primitive response contracts", () => {
  it.each([
    ["single_choice", ""],
    ["graded_choice", ""],
    ["self_grade", ""],
    ["text", ""],
    ["short_text", ""],
    ["audio_ref", ""],
    ["selection", []],
    ["tokens", []],
    ["ordered_items", []],
    ["spans", []],
    ["pairing", {}],
    ["grouping", {}],
    ["cells", {}],
    ["self_assessment", {}],
    ["acknowledgement", true],
  ] as const)("creates a valid empty %s response", (kind, expected) => {
    expect(emptyResponse(kind)).toEqual(expected);
  });

  it("normalizes token entry without preserving empty slots", () => {
    expect(normalizeResponse("tokens", "  sono, molto   stanco ")).toEqual([
      "sono",
      "molto",
      "stanco",
    ]);
  });

  it("keeps structured answers immutable at submission boundaries", () => {
    const pairing = { buongiorno: "bonjour" };
    const normalized = normalizeResponse("pairing", pairing);

    pairing.buongiorno = "salut";
    expect(normalized).toEqual({ buongiorno: "bonjour" });
  });

  it("rejects incomplete structured answers", () => {
    expect(isResponseComplete("pairing", { a: "b", c: "" })).toBe(false);
    expect(isResponseComplete("cells", { io: "sono", tu: "sei" })).toBe(true);
    expect(isResponseComplete("selection", [])).toBe(false);
    expect(isResponseComplete("acknowledgement", true)).toBe(true);
    expect(isResponseComplete("spans", [[0, 4]])).toBe(true);
    expect(isResponseComplete("spans", ["0:4"])).toBe(false);
    expect(isResponseComplete("tokens", ["sono", "qui"])).toBe(true);
    expect(isResponseComplete("tokens", [1, 2])).toBe(false);
  });
});
