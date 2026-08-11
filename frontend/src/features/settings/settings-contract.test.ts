import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("settings API contracts", () => {
  it("requests only the boolean export scopes accepted by the backend", () => {
    const source = readFileSync(
      resolve(import.meta.dirname, "settings-page.tsx"),
      "utf8",
    );

    expect(source).toContain("learning_history: true");
    expect(source).toContain("memory_prompts: true");
    expect(source).toContain("vocabulary_lists: true");
    expect(source).toContain("word_bank: true");
    expect(source).not.toContain('format: "json"');
    expect(source).not.toContain("include:");
    expect(source).toContain('to="/login?returnTo=/settings"');
    expect(source).toContain("Votre identité doit être vérifiée");
  });
});
