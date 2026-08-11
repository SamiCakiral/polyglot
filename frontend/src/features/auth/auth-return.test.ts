import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { safeReturnTo } from "./auth-return";

describe("safeReturnTo", () => {
  it("accepts an internal application path", () => {
    expect(safeReturnTo("/settings")).toBe("/settings");
  });

  it("rejects external and protocol-relative destinations", () => {
    expect(safeReturnTo("https://example.test/settings")).toBeNull();
    expect(safeReturnTo("//example.test/settings")).toBeNull();
    expect(safeReturnTo("/\\example.test/settings")).toBeNull();
    expect(safeReturnTo("/settings\nignored")).toBeNull();
    expect(safeReturnTo("settings")).toBeNull();
  });

  it("replaces the cached session after authentication", () => {
    const source = readFileSync(
      resolve(import.meta.dirname, "auth-page.tsx"),
      "utf8",
    );

    expect(source).toContain("queryClient.clear()");
    expect(source).toContain("window.location.replace(destination)");
    expect(source).not.toContain("queryClient.setQueryData");
  });
});
