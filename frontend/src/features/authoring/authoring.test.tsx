import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, expect, it } from "vitest";

import { renderShell } from "../../shell/test-utils";
import { currentSessionFixture, server } from "../../../tests/support/server";

afterEach(cleanup);

function useAuthorSession() {
  server.use(
    http.get("*/api/v1/session", () =>
      HttpResponse.json({ ...currentSessionFixture, roles: ["author"] }),
    ),
  );
}

it("refuses authoring surfaces to a learner", async () => {
  renderShell("/authoring");

  expect(await screen.findByRole("alert")).toHaveTextContent("Atelier réservé");
  expect(
    screen.queryByRole("navigation", { name: "Navigation de l'Atelier" }),
  ).not.toBeInTheDocument();
});

it("shows the editorial navigation to an author", async () => {
  useAuthorSession();
  renderShell("/authoring");

  expect(await screen.findByRole("heading", { name: "Atelier" })).toBeVisible();
  expect(
    screen.getByRole("navigation", { name: "Navigation de l'Atelier" }),
  ).toBeVisible();
  expect(screen.getByRole("link", { name: /Outils contrôlés/ })).toBeVisible();
});

it("renders closed tool inputs and validates an invocation", async () => {
  useAuthorSession();
  server.use(
    http.get("*/api/v1/tools", () =>
      HttpResponse.json([
        {
          effect: "none",
          input_schema: {
            type: "object",
            additionalProperties: false,
            required: ["pack_revision_id"],
            properties: { pack_revision_id: {} },
          },
          max_input_bytes: 1024,
          max_output_bytes: 2048,
          name: "catalogue.list_targets",
          output_schema: {
            type: "object",
            additionalProperties: false,
            required: ["targets", "next_cursor", "stable"],
            properties: { targets: {}, next_cursor: {}, stable: {} },
          },
          roles: ["author"],
          timeout_ms: 10000,
          version: "1.0.0",
        },
      ]),
    ),
    http.post("*/api/v1/tools/catalogue.list_targets:invoke", () =>
      HttpResponse.json({
        invocation_id: "019fe900-6000-7000-8000-000000000099",
        output: { targets: [], next_cursor: null, stable: true },
        status: "succeeded",
        tool_name: "catalogue.list_targets",
        tool_version: "1.0.0",
      }),
    ),
  );
  const user = userEvent.setup();
  renderShell("/authoring/tools");

  const input = await screen.findByRole("textbox", { name: "pack_revision_id" });
  await user.type(input, "019b0000-0000-7000-8000-000000000009");
  await user.click(screen.getByRole("button", { name: "Exécuter" }));

  expect(await screen.findByText("Sortie validée")).toBeVisible();
  expect(screen.getByText(/stable/)).toBeVisible();
});

it("shows a locally generated artifact to an author", async () => {
  useAuthorSession();
  const artifactId = "019fe900-6000-7000-8000-000000000088";
  server.use(
    http.post("*/api/v1/generation-jobs", () =>
      HttpResponse.json(
        {
          attempt_count: 0,
          error_code: null,
          finished_at: null,
          job_id: "019fe900-6000-7000-8000-000000000077",
          max_attempts: 1,
          model_code: "qwen/qwen3.6-35b-a3b",
          prompt_revision: "POLYGLOT_AUTHOR_V1",
          provider_code: "lm_studio",
          requested_at: "2026-08-11T12:00:00Z",
          requested_by_actor_id: currentSessionFixture.account_id,
          result_draft_id: null,
          started_at: null,
          status: "requested",
          task_type: "exercise_draft",
          tool_allowlist: ["exercise.submit_draft@1.0.0"],
          version: 1,
        },
        { status: 201 },
      ),
    ),
    http.get("*/api/v1/jobs/:id", () =>
      HttpResponse.json({
        attempt_count: 1,
        error_code: null,
        finished_at: "2026-08-11T12:00:02Z",
        job_id: "019fe900-6000-7000-8000-000000000077",
        max_attempts: 1,
        model_code: "qwen/qwen3.6-35b-a3b",
        prompt_revision: "POLYGLOT_AUTHOR_V1",
        provider_code: "lm_studio",
        requested_at: "2026-08-11T12:00:00Z",
        requested_by_actor_id: currentSessionFixture.account_id,
        result_draft_id: artifactId,
        started_at: "2026-08-11T12:00:01Z",
        status: "succeeded",
        task_type: "exercise_draft",
        tool_allowlist: ["exercise.submit_draft@1.0.0"],
        version: 3,
      }),
    ),
    http.get("*/api/v1/authoring-artifacts", () =>
      HttpResponse.json([
        {
          artifact_id: artifactId,
          artifact_type: "exercise",
          checksum: "a".repeat(64),
          created_at: "2026-08-11T12:00:02Z",
          payload: { status: "draft", title: "In treno" },
          source_tool_name: "exercise.submit_draft",
          status: "draft",
        },
      ]),
    ),
    http.get("*/api/v1/language-packs", () =>
      HttpResponse.json({
        items: [
          {
            pack_id: "019fe900-6000-7000-8000-000000000055",
            target_variety_id: "019fe900-6000-7000-8000-000000000056",
          },
        ],
        next_cursor: null,
      }),
    ),
    http.post("*/api/v1/authoring/drafts", () =>
      HttpResponse.json(
        {
          content_revision_id: "019fe900-6000-7000-8000-000000000099",
        },
        { status: 201 },
      ),
    ),
  );
  const user = userEvent.setup();
  renderShell("/authoring/generate");

  await user.click(
    await screen.findByRole("button", { name: "Générer l'artefact" }),
  );

  expect(await screen.findByText("succeeded")).toBeVisible();
  expect(await screen.findByText(/In treno/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Adopter comme brouillon" }));
  expect(await screen.findByRole("link", { name: "Ouvrir la revue" })).toBeVisible();
});
