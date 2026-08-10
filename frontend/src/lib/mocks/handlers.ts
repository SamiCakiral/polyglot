import {
  getGetCurrentSessionMockHandler,
  getGetCurrentSessionResponseMock,
  getPolyglotV2APIMock,
} from "../../generated/mocks/polyglot.msw";

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

export const handlers = [
  getGetCurrentSessionMockHandler(session),
  ...getPolyglotV2APIMock(),
];
