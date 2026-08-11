import { cleanup, screen, within } from "@testing-library/react";
import { HttpResponse, http, type JsonBodyType } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { server } from "../../../tests/support/server";
import { renderShell } from "../../shell/test-utils";

const profileId = "019fe900-6000-7000-8000-000000000010";
const supportVarietyId = "019b0000-0000-7000-8000-000000000005";
const targetVarietyId = "019b0000-0000-7000-8000-000000000002";

function useProfileHandlers(onboarding: JsonBodyType, status = 200): void {
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
            goals: ["Tenir une conversation"],
            interests: [],
            native_variety_id: supportVarietyId,
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
            channel: "stable",
            compatibility_range: ">=2.0.0,<2.1.0",
            foundation_revision_id: "019b0000-0000-7000-8000-000000000901",
            pack_code: "it-IT__fr-FR",
            pack_id: "019b0000-0000-7000-8000-000000000008",
            pack_revision_id: "019b0000-0000-7000-8000-000000000009",
            revision_no: 1,
            support_language_tags: ["fr-FR"],
            support_variety_ids: [supportVarietyId],
            target_language_tag: "it-IT",
            target_variety_id: targetVarietyId,
          },
        ],
        next_cursor: null,
      }),
    ),
    http.get("*/api/v1/account-languages", () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get("*/api/v1/modules", () => HttpResponse.json([])),
    http.get("*/api/v1/language-profiles/:profileId/onboarding", () =>
      status === 200
        ? HttpResponse.json(onboarding)
        : HttpResponse.json(
            {
              code: "resource_not_found",
              detail: "No onboarding state exists.",
              status: 404,
              title: "resource_not_found",
              type: "about:blank",
            },
            { status },
          ),
    ),
  );
}

afterEach(cleanup);

describe("multilingual onboarding", () => {
  it("offers the three non-blocking entry paths when no placement exists", async () => {
    useProfileHandlers(null, 404);

    renderShell("/language-profile");

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: /Où en êtes-vous en italien/,
      }),
    ).toBeVisible();
    const choices = screen.getByRole("region", {
      name: "Choisir un point de départ",
    });
    expect(within(choices).getByRole("button", { name: /Je pars de zéro/ })).toBeVisible();
    expect(within(choices).getByRole("button", { name: /J'ai déjà commencé/ })).toBeVisible();
    expect(within(choices).getByRole("button", { name: /Je suis déjà autonome/ })).toBeVisible();
  });

  it("shows uncertainty per skill and lets the learner override placement", async () => {
    useProfileHandlers({
      calibration_sessions_remaining: 3,
      can_train: true,
      created_at: "2026-08-10T08:00:00Z",
      detected_band: "functional",
      entry_path: "already_started",
      is_provisional: true,
      placement_choice: null,
      placement_confidence: 0.74,
      profile_id: profileId,
      resolved_band: "functional",
      skill_profile: [
        {
          band: "functional",
          confidence: 0.8,
          dimension: "reading",
          evidence_count: 2,
        },
        {
          band: "foundations",
          confidence: 0,
          dimension: "listening",
          evidence_count: 0,
        },
      ],
      updated_at: "2026-08-10T08:10:00Z",
      version: 2,
    });

    renderShell("/language-profile");

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Point de départ : Fonctionnel",
      }),
    ).toBeVisible();
    expect(screen.getByText("74% de confiance")).toBeVisible();
    const skillMap = screen.getByRole("region", {
      name: "Carte des compétences détectées",
    });
    expect(within(skillMap).getByText("80% de confiance")).toBeVisible();
    expect(within(skillMap).getByText("à calibrer")).toBeVisible();
    expect(screen.getByRole("button", { name: "Commencer plus doucement" })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Accepter et s'entraîner/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Me mettre au défi" })).toBeEnabled();
  });
});
