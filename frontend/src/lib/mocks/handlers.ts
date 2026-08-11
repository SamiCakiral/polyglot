import {
  getGetCurrentSessionMockHandler,
  getGetCurrentSessionResponseMock,
  getPolyglotV2APIMock,
} from "../../generated/mocks/polyglot.msw";
import { HttpResponse, http } from "msw";

const session = getGetCurrentSessionResponseMock({
  account_id: "019fe900-6000-7000-8000-000000000001",
  session_id: "019fe900-6000-7000-8000-000000000002",
  roles: ["learner"],
  csrf_token: "synthetic-browser-csrf-token",
  idle_expires_at: "2026-08-10T22:00:00Z",
  absolute_expires_at: "2026-08-17T10:00:00Z",
  consents: [],
  preferences: {
    account_id: "019fe900-6000-7000-8000-000000000001",
    interface_locale: "fr-FR",
    timezone: "Europe/Paris",
    day_cutover_local_time: "04:00:00",
    preferred_sprint_minutes: 30,
    accessibility_preferences: {},
    media_preferences: {},
    version: 1,
    updated_at: "2026-08-10T10:00:00Z",
  },
});

const profileFixture = {
  account_id: session.account_id,
  archived_at: null,
  created_at: "2026-08-01T08:00:00Z",
  current_phase: "active",
  deleted_at: null,
  excluded_themes: [],
  goals: ["Voyager avec autonomie", "Tenir une conversation"],
  interests: ["culture", "vie quotidienne"],
  native_variety_id: "019b0000-0000-7000-8000-000000000005",
  profile_id: "019fe900-6000-7000-8000-000000000010",
  status: "active",
  target_variety_id: "019b0000-0000-7000-8000-000000000002",
  updated_at: "2026-08-10T08:00:00Z",
  version: 2,
};

let hasProfile = true;
let currentProfile = { ...profileFixture };
let accountLanguages: Record<string, unknown>[] = [];
let onboardingState: Record<string, unknown> | null = {
  calibration_sessions_remaining: 2,
  can_train: true,
  created_at: "2026-08-10T08:00:00Z",
  detected_band: "functional",
  entry_path: "already_started",
  is_provisional: true,
  placement_choice: "accept",
  placement_confidence: 0.74,
  profile_id: profileFixture.profile_id,
  resolved_band: "functional",
  skill_profile: [],
  updated_at: "2026-08-10T08:10:00Z",
  version: 3,
};

const canonicalHandlers = [
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
          support_variety_ids: ["019b0000-0000-7000-8000-000000000005"],
          target_language_tag: "it-IT",
          target_variety_id: "019b0000-0000-7000-8000-000000000002",
        },
      ],
      next_cursor: null,
    }),
  ),
  http.post("*/api/v1/accounts", () => {
    hasProfile = false;
    accountLanguages = [];
    onboardingState = null;
    currentProfile = { ...profileFixture };
    return HttpResponse.json(
      { account_id: session.account_id, version: 1 },
      { status: 201 },
    );
  }),
  http.post("*/api/v1/session", () =>
    HttpResponse.json(
      {
        absolute_expires_at: session.absolute_expires_at,
        account_id: session.account_id,
        csrf_token: session.csrf_token,
        idle_expires_at: session.idle_expires_at,
        roles: session.roles,
        session_id: session.session_id,
      },
      { status: 201 },
    ),
  ),
  http.get("*/api/v1/language-profiles", () =>
    HttpResponse.json({ items: hasProfile ? [currentProfile] : [] }),
  ),
  http.post("*/api/v1/language-profiles", () => {
    hasProfile = true;
    currentProfile = {
      ...profileFixture,
      current_phase: "diagnostic",
      goals: [],
      status: "onboarding",
      version: 1,
    };
    return HttpResponse.json(
      currentProfile,
      { status: 201 },
    );
  }),
  http.patch(
    "*/api/v1/language-profiles/:profileId/goals",
    async ({ request }) => {
      const body = (await request.json()) as { goals?: string[] };
      currentProfile = {
        ...currentProfile,
        goals: body.goals ?? currentProfile.goals,
        version: 3,
      };
      return HttpResponse.json(currentProfile);
    },
  ),
  http.get("*/api/v1/account-languages", () =>
    HttpResponse.json({ items: accountLanguages, next_cursor: null }),
  ),
  http.post("*/api/v1/account-languages", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const language = {
      ...body,
      account_language_id: `019fe900-6000-7000-8000-${String(accountLanguages.length + 20).padStart(12, "0")}`,
      archived_at: null,
      created_at: "2026-08-10T08:00:00Z",
      grants_mastery: false,
      updated_at: "2026-08-10T08:00:00Z",
      version: 1,
    };
    accountLanguages = [...accountLanguages, language];
    return HttpResponse.json(language, { status: 201 });
  }),
  http.get("*/api/v1/language-profiles/:profileId/onboarding", () =>
    onboardingState
      ? HttpResponse.json(onboardingState)
      : HttpResponse.json(
          { title: "Not found", status: 404, detail: "Onboarding not started." },
          { status: 404 },
        ),
  ),
  http.put(
    "*/api/v1/language-profiles/:profileId/onboarding",
    async ({ request }) => {
      const body = (await request.json()) as { entry_path: string };
      onboardingState = {
        calibration_sessions_remaining: 3,
        can_train: true,
        created_at: "2026-08-10T08:00:00Z",
        detected_band: null,
        entry_path: body.entry_path,
        is_provisional: true,
        placement_choice: null,
        placement_confidence: null,
        profile_id: profileFixture.profile_id,
        resolved_band:
          body.entry_path === "complete_beginner" ? "foundations" : "emerging",
        skill_profile: [],
        updated_at: "2026-08-10T08:00:00Z",
        version: 1,
      };
      return HttpResponse.json(onboardingState);
    },
  ),
  http.post(
    "*/api/v1/language-profiles/:profileId/onboarding:choose",
    async ({ request }) => {
      const body = (await request.json()) as { choice: string };
      onboardingState = {
        ...onboardingState,
        placement_choice: body.choice,
        updated_at: "2026-08-10T08:15:00Z",
        version: 2,
      };
      currentProfile = {
        ...currentProfile,
        current_phase: "active",
        status: "active",
        version: currentProfile.version + 1,
      };
      return HttpResponse.json(onboardingState);
    },
  ),
  http.get("*/api/v1/modules", () =>
    HttpResponse.json([
      {
        entry_profile_codes: ["foundation_complete"],
        max_days: 10,
        max_minutes: 60,
        min_minutes: 10,
        module_code: "ARRIVARE_IN_ITALIA",
        module_id: "module-fixture",
        module_revision_id: "019fe900-6000-7000-8000-000000000031",
        nominal_days: 7,
        primary_intention: "Arriver, s'orienter et gérer les premiers imprévus",
      },
    ]),
  ),
  http.get("*/api/v1/language-profiles/:profileId/word-bank", () =>
    HttpResponse.json({
      encountered_sense_count: 3,
      items: [
        {
          analysis_state: "resolved",
          encounter_count: 5,
          familiarity_declaration: null,
          first_encountered_at: "2026-08-01T08:00:00Z",
          label: "binario",
          last_encountered_at: "2026-08-10T08:00:00Z",
          learning_preference: "automatic",
          reasons: ["À réactiver dans une nouvelle situation"],
          sense_id: "019fe900-6000-7000-8000-000000000041",
        },
        {
          analysis_state: "resolved",
          encounter_count: 3,
          familiarity_declaration: null,
          first_encountered_at: "2026-08-03T08:00:00Z",
          label: "ritardo",
          last_encountered_at: "2026-08-09T08:00:00Z",
          learning_preference: "automatic",
          reasons: ["Compris mais rarement produit"],
          sense_id: "019fe900-6000-7000-8000-000000000042",
        },
        {
          analysis_state: "resolved",
          encounter_count: 2,
          familiarity_declaration: null,
          first_encountered_at: "2026-08-05T08:00:00Z",
          label: "coincidenza",
          last_encountered_at: "2026-08-08T08:00:00Z",
          learning_preference: "automatic",
          reasons: ["Nouveau mot du module"],
          sense_id: "019fe900-6000-7000-8000-000000000043",
        },
      ],
      next_cursor: null,
      reference_coverage_count: 3,
      reference_revision: "it-core-1",
      reference_set_code: "it-core",
      reference_total_count: 5000,
      unresolved_mention_count: 0,
    }),
  ),
  http.get("*/api/v1/language-profiles/:profileId/progress", () =>
    HttpResponse.json({
      facets: [],
      has_global_score: false,
      modalities: [
        {
          confidence: 0.72,
          coverage: 0.31,
          expected_facet_count: 40,
          freshness: 0.9,
          modality: "reading",
          observed_facet_count: 12,
          score: 0.64,
          status: "reliable",
        },
        {
          confidence: 0.58,
          coverage: 0.22,
          expected_facet_count: 40,
          freshness: 0.82,
          modality: "listening",
          observed_facet_count: 9,
          score: 0.51,
          status: "in_progress",
        },
        {
          confidence: 0.48,
          coverage: 0.18,
          expected_facet_count: 40,
          freshness: 0.76,
          modality: "writing",
          observed_facet_count: 7,
          score: 0.43,
          status: "in_progress",
        },
        {
          confidence: 0,
          coverage: 0,
          expected_facet_count: 40,
          freshness: null,
          modality: "speaking",
          observed_facet_count: 0,
          score: null,
          status: "not_evaluable",
        },
      ],
      next_cursor: null,
      policy_revision: "mastery-v1",
          profile_id: profileFixture.profile_id,
    }),
  ),
];

export const handlers = [
  getGetCurrentSessionMockHandler(session),
  ...canonicalHandlers,
  ...getPolyglotV2APIMock(),
];
