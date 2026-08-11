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
