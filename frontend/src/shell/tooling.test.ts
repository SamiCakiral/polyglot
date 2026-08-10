import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const frontendRoot = resolve(import.meta.dirname, "../..");
const repositoryRoot = resolve(frontendRoot, "..");

describe("W17 frontend baseline", () => {
  it("pins the exact supported Node and pnpm runtime", () => {
    const nodeVersionPath = resolve(repositoryRoot, ".node-version");
    expect(existsSync(nodeVersionPath)).toBe(true);

    const packageJson = JSON.parse(
      readFileSync(resolve(frontendRoot, "package.json"), "utf8"),
    ) as {
      engines: { node: string; pnpm?: string };
      packageManager: string;
      scripts: { build: string };
    };

    expect(readFileSync(nodeVersionPath, "utf8").trim()).toBe("22.18.0");
    expect(packageJson.engines).toEqual({ node: "22.18.0", pnpm: "11.16.0" });
    expect(packageJson.packageManager).toBe("pnpm@11.16.0");
    expect(packageJson.scripts.build).not.toContain("pnpm run");
  });

  it("runs the locked frontend quality and generated-client gates in CI", () => {
    const ci = readFileSync(resolve(repositoryRoot, ".github/workflows/ci.yml"), "utf8");

    expect(ci).toContain("frontend-quality:");
    expect(ci).toContain("node-version-file: .node-version");
    expect(ci).toContain("pnpm --dir frontend install --frozen-lockfile");
    expect(ci).toContain("git diff --exit-code -- frontend/src/generated");
    expect(ci).toContain("pnpm --dir frontend lint");
    expect(ci).toContain("pnpm --dir frontend typecheck");
    expect(ci).toContain("pnpm --dir frontend test --run");
    expect(ci).toContain("pnpm --dir frontend build");
    expect(ci).toContain("pnpm --dir frontend exec playwright test");
  });

  it("does not disable axe color contrast in shell tests", () => {
    const accessibilityTest = readFileSync(
      resolve(frontendRoot, "src/shell/accessibility.test.tsx"),
      "utf8",
    );

    expect(accessibilityTest).not.toContain('"color-contrast": { enabled: false }');
  });

  it("keeps Playwright specifications outside Vitest collection", () => {
    const viteConfig = readFileSync(resolve(frontendRoot, "vite.config.ts"), "utf8");

    expect(viteConfig).toContain(
      'exclude: [...configDefaults.exclude, "tests/e2e/**"]',
    );
  });
});
