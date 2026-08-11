import { describe, expect, it } from "vitest";

import { languageDisplayName } from "./language-display";

describe("language display names", () => {
  it("names Japanese and French from their BCP 47 tags", () => {
    expect(languageDisplayName("ja-JP", "fr-FR")).toBe("japonais");
    expect(languageDisplayName("fr-FR", "fr-FR")).toBe("français");
  });

  it("keeps an unknown tag visible instead of inventing a language", () => {
    expect(languageDisplayName("x-polyglot", "fr-FR")).toBe("x-polyglot");
  });
});
