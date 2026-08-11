import { describe, expect, it } from "vitest";

import { uuid7 } from "./ids";
import { commandFetch } from "./api";

describe("uuid7", () => {
  it("creates RFC 9562 version 7 identifiers", () => {
    const value = uuid7();

    expect(value).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it("does not reuse identifiers created in the same millisecond", () => {
    expect(new Set(Array.from({ length: 64 }, uuid7))).toHaveLength(64);
  });
});

describe("commandFetch", () => {
  it("keeps generated-client command headers enumerable", () => {
    const request = commandFetch(
      { csrf_token: "csrf-proof" } as Parameters<typeof commandFetch>[0],
      4,
    );
    expect(request.headers).toMatchObject({
      "X-CSRF-Token": "csrf-proof",
      "If-Match": '"4"',
    });
    expect(Object.keys(request.headers as Record<string, string>)).toContain("Idempotency-Key");
  });
});
