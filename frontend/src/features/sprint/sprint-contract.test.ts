import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import type { SprintBlockResponse } from "../../generated/model";
import { sprintFamilyLabel } from "./sprint-family-label";
import { resumeBlockOffset } from "./sprint-position";

describe("sprint completion contract", () => {
  it("sends the empty request accepted by the completion endpoint", () => {
    const source = readFileSync(
      resolve(import.meta.dirname, "sprint-page.tsx"),
      "utf8",
    );

    expect(source).toContain("completeSprintRun(\n      runId,\n      {},");
    expect(source).not.toContain('reason: "completed_by_learner"');
  });

  it("refreshes the run version before a terminal transition", () => {
    const source = readFileSync(
      resolve(import.meta.dirname, "sprint-page.tsx"),
      "utf8",
    );

    expect(source).toContain("await query.refetch()");
    expect(source).toContain("commandFetch(session, latestRun.data.version)");
  });

  it("keeps internal primitive identifiers out of the learner view", () => {
    const source = readFileSync(
      resolve(import.meta.dirname, "sprint-page.tsx"),
      "utf8",
    );

    expect(source).not.toContain("exercise.primitive_id.replaceAll");
  });

  it("names comprehension from the active target language", () => {
    expect(sprintFamilyLabel("version_input", "ja-JP")).toBe(
      "Comprendre le japonais",
    );
    expect(sprintFamilyLabel("version", "it-IT")).toBe(
      "Comprendre l’italien",
    );
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
