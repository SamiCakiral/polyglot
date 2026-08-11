import { cleanup, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, expect, it } from "vitest";

import { server } from "../../../tests/support/server";
import { renderShell } from "../../shell/test-utils";

afterEach(cleanup);

it("requests and shows only modules from the active Japanese pack", async () => {
  const targetVarietyId = "019fe900-6000-7000-8000-000000000251";
  const packRevisionId = "019fe900-6000-7000-8000-000000000252";
  server.use(
    http.get("*/api/v1/language-profiles", () =>
      HttpResponse.json({
        items: [
          {
            account_id: "019fe900-6000-7000-8000-000000000001",
            archived_at: null,
            created_at: "2026-08-11T08:00:00Z",
            current_phase: "active",
            deleted_at: null,
            excluded_themes: [],
            goals: [],
            interests: [],
            native_variety_id: "019fe900-6000-7000-8000-000000000253",
            profile_id: "019fe900-6000-7000-8000-000000000254",
            status: "active",
            target_variety_id: targetVarietyId,
            updated_at: "2026-08-11T08:00:00Z",
            version: 1,
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
            pack_code: "ja-JP__fr-FR",
            pack_id: "019fe900-6000-7000-8000-000000000255",
            pack_revision_id: packRevisionId,
            revision_no: 1,
            segmentation_policy_revision_id:
              "019fe900-6000-7000-8000-000000000256",
            support_language_tags: ["fr-FR"],
            support_variety_ids: [
              "019fe900-6000-7000-8000-000000000253",
            ],
            target_language_tag: "ja-JP",
            target_script_codes: ["Hira", "Kana", "Jpan"],
            target_variety_id: targetVarietyId,
            text_direction: "ltr",
          },
        ],
        next_cursor: null,
      }),
    ),
    http.get("*/api/v1/modules", ({ request }) => {
      const requestedPack = new URL(request.url).searchParams.get(
        "pack_revision_id",
      );
      return HttpResponse.json(
        requestedPack === packRevisionId
          ? [
              {
                entry_profile_codes: ["foundation"],
                max_days: 3,
                max_minutes: 60,
                min_minutes: 10,
                module_code: "JA-SURVIVAL-FOUNDATIONS",
                module_id: "019fe900-6000-7000-8000-000000000257",
                module_revision_id:
                  "019fe900-6000-7000-8000-000000000258",
                nominal_days: 3,
                pack_revision_id: packRevisionId,
                primary_intention:
                  "Décoder les kana et accomplir des échanges de survie polis",
              },
            ]
          : [
              {
                entry_profile_codes: ["foundation"],
                max_days: 3,
                max_minutes: 60,
                min_minutes: 10,
                module_code: "IT-FIRST-AUTONOMOUS-EXCHANGE",
                module_id: "019fe900-6000-7000-8000-000000000259",
                module_revision_id:
                  "019fe900-6000-7000-8000-000000000260",
                nominal_days: 3,
                pack_revision_id:
                  "019fe900-6000-7000-8000-000000000261",
                primary_intention: "Premiers échanges autonomes",
              },
            ],
      );
    }),
  );

  renderShell("/learn");

  expect(
    await screen.findByRole("heading", {
      name: "Décoder les kana et accomplir des échanges de survie polis",
    }),
  ).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "Premiers échanges autonomes" }),
  ).not.toBeInTheDocument();
});
