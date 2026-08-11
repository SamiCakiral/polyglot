import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import type { SprintBlockResponse } from "../../generated/model";
import { resumeBlockOffset } from "./sprint-position";

describe("sprint completion contract", () => {
  it("sends the empty request accepted by the completion endpoint", () => {
    const source = readFileSync(
      resolve(import.meta.dirname, "sprint-page.tsx"),
      "utf8",
    );

    expect(source).toContain('runId,\n      data: {},');
    expect(source).not.toContain('reason: "completed_by_learner"');
  });

  it("resumes at the first unfinished block after a reload", () => {
    const blocks = [
      { status: "completed", session_plan_block_id: "one" },
      { status: "completed", session_plan_block_id: "two" },
      { status: "available", session_plan_block_id: "reflection" },
    ] as SprintBlockResponse[];

    expect(resumeBlockOffset(blocks, null)).toBe(2);
    expect(resumeBlockOffset(blocks, "two")).toBe(1);
  });
});
