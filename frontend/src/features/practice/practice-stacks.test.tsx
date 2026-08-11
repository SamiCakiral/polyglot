import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { server } from "../../../tests/support/server";
import { renderShell } from "../../shell/test-utils";

const profileId = "019fe900-6000-7000-8000-000000000010";
const targetVarietyId = "019b0000-0000-7000-8000-000000000002";
const packRevisionId = "019b0000-0000-7000-8000-000000000009";

function useLanguageContext(): void {
  server.use(
    http.get("*/api/v1/language-profiles", () =>
      HttpResponse.json({
        items: [
          {
            account_id: "019fe900-6000-7000-8000-000000000001",
            archived_at: null,
            created_at: "2026-08-01T08:00:00Z",
            current_phase: "active",
            deleted_at: null,
            excluded_themes: [],
            goals: [],
            interests: [],
            native_variety_id: "019b0000-0000-7000-8000-000000000005",
            profile_id: profileId,
            status: "active",
            target_variety_id: targetVarietyId,
            updated_at: "2026-08-10T08:00:00Z",
            version: 2,
          },
        ],
      }),
    ),
    http.get("*/api/v1/language-packs", () =>
      HttpResponse.json({
        items: [
          {
            capability_manifest: { schema_version: 1 },
            channel: "stable",
            compatibility_range: ">=2.0.0,<2.1.0",
            foundation_revision_id: null,
            media_capabilities: { schema_version: 1 },
            pack_code: "it-IT__fr-FR",
            pack_id: "019b0000-0000-7000-8000-000000000008",
            pack_revision_id: packRevisionId,
            revision_no: 1,
            segmentation_policy_revision_id:
              "019b0000-0000-7000-8000-000000000006",
            support_language_tags: ["fr-FR"],
            support_variety_ids: ["019b0000-0000-7000-8000-000000000005"],
            target_language_tag: "it-IT",
            target_script_codes: ["Latn"],
            target_variety_id: targetVarietyId,
            text_direction: "ltr",
          },
        ],
        next_cursor: null,
      }),
    ),
    http.get("*/api/v1/account-languages", () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

afterEach(cleanup);

describe("personal practice stacks", () => {
  it("shows exact saved stacks before free practice", async () => {
    useLanguageContext();
    server.use(
      http.get("*/api/v1/language-profiles/:profileId/practice-stacks", () =>
        HttpResponse.json({
          items: [
            {
              checksum: "a".repeat(64),
              created_at: "2026-08-11T08:00:00Z",
              language_pack_revision_id: packRevisionId,
              members: [
                {
                  definition: "la voie de chemin de fer",
                  label: "binario",
                  sense_id: "019fe900-6000-7000-8000-000000000041",
                  sense_revision_id: "019fe900-6000-7000-8000-000000000042",
                  source_kind: "daily",
                  source_ref: "module_day:1",
                },
              ],
              name: "Arrivée à la gare - J1",
              pedagogical_day: "2026-08-11",
              profile_id: profileId,
              source_refs: ["module_day:1"],
              stack_id: "019fe900-6000-7000-8000-000000000043",
              stack_kind: "daily",
            },
          ],
        }),
      ),
    );

    renderShell("/practice");

    expect(
      await screen.findByRole("heading", { name: "Piles disponibles" }),
    ).toBeVisible();
    expect(await screen.findByText("Arrivée à la gare - J1")).toBeVisible();
    expect(
      screen.getByRole("button", { name: /Entraîner cette pile/ }),
    ).toBeEnabled();
  });

  it("reveals a frozen card without claiming mastery", async () => {
    useLanguageContext();
    server.use(
      http.get("*/api/v1/practice-runs/:runId", () =>
        HttpResponse.json({
          completed_at: null,
          current_item: {
            definition: "la voie de chemin de fer",
            label: "binario",
            sense_id: "019fe900-6000-7000-8000-000000000041",
            sense_revision_id: "019fe900-6000-7000-8000-000000000042",
            source_kind: "daily",
            source_ref: "module_day:1",
          },
          current_position: 0,
          direction: "target_to_support",
          member_count: 1,
          mode: "cards",
          preset_id: "019fe900-6000-7000-8000-000000000043",
          preset_revision_id: "019fe900-6000-7000-8000-000000000044",
          profile_id: profileId,
          run_id: "019fe900-6000-7000-8000-000000000045",
          started_at: "2026-08-11T08:00:00Z",
          status: "in_progress",
          updated_at: "2026-08-11T08:00:00Z",
          version: 1,
        }),
      ),
    );

    renderShell("/practice/runs/019fe900-6000-7000-8000-000000000045");

    expect(
      await screen.findByRole("heading", { name: "binario" }),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Retourner la carte" }),
    );
    expect(screen.getByText("la voie de chemin de fer")).toBeVisible();
  });

  it("does not advance when the memory review was not persisted", async () => {
    useLanguageContext();
    let advanceCalls = 0;
    const runId = "019fe900-6000-7000-8000-000000000055";
    const prompt = {
      direction: "it-IT->fr-FR",
      modality: "reading",
      operation: "recognition",
      profile_id: profileId,
      prompt_id: "019fe900-6000-7000-8000-000000000056",
      protocol_id: "practice-stack-self-recall",
      protocol_revision: 1,
      schedule: {
        due_at: "2026-08-11T08:00:00Z",
        lapses: 0,
        parameter_set_id: "fsrs-test",
        policy_revision: 1,
        projection_version: 1,
        reps: 0,
        scheduler_kind: "fsrs",
        scheduler_version: "6.3.1",
        state: "new",
      },
      status: "active",
      target_ref: "019fe900-6000-7000-8000-000000000041",
      target_revision_id: "019fe900-6000-7000-8000-000000000042",
      version: 1,
    };
    server.use(
      http.get("*/api/v1/practice-runs/:runId", () =>
        HttpResponse.json({
          completed_at: null,
          current_item: {
            definition: "la voie de chemin de fer",
            label: "binario",
            sense_id: prompt.target_ref,
            sense_revision_id: prompt.target_revision_id,
            source_kind: "daily",
            source_ref: "module_day:1",
          },
          current_position: 0,
          direction: "target_to_support",
          member_count: 1,
          mode: "cards",
          preset_id: "019fe900-6000-7000-8000-000000000053",
          preset_revision_id: "019fe900-6000-7000-8000-000000000054",
          profile_id: profileId,
          run_id: runId,
          started_at: "2026-08-11T08:00:00Z",
          status: "in_progress",
          updated_at: "2026-08-11T08:00:00Z",
          version: 1,
        }),
      ),
      http.get("*/api/v1/language-profiles/:profileId/memory-prompts", () =>
        HttpResponse.json({ items: [prompt] }),
      ),
      http.post("*/api/v1/memory-prompts/:promptId/reviews", () =>
        HttpResponse.json(prompt),
      ),
      http.post(/\/api\/v1\/practice-runs\/[^/]+:advance$/, () => {
        advanceCalls += 1;
        return HttpResponse.json({});
      }),
    );

    renderShell(`/practice/runs/${runId}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Retourner la carte" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Correct" }));

    expect(
      await screen.findByText(
        "La révision n'a pas produit de nouvelle planification.",
      ),
    ).toBeVisible();
    expect(advanceCalls).toBe(0);
  });
});
