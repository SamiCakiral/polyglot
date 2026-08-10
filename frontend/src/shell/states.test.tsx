import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http } from "msw";
import { expect, it } from "vitest";

import type { ProblemResponse } from "../generated/model";
import { server } from "../../tests/support/server";
import { renderShell, renderWithErrorBoundary } from "./test-utils";

it("reserves a stable shell loading state while the generated session query is pending", () => {
  server.use(
    http.get("*/api/v1/session", async () => {
      await delay("infinite");
      return HttpResponse.json({});
    }),
  );

  renderShell();

  expect(screen.getByRole("status", { name: "Chargement de Polyglot" })).toBeVisible();
});

it("renders a recoverable shell error when the generated session endpoint fails", async () => {
  const problem: ProblemResponse = {
    type: "about:blank",
    title: "Dependency unavailable",
    status: 503,
    detail: "The session service is unavailable.",
    instance: "/api/v1/session",
    code: "dependency_unavailable",
    message_key: "errors.dependency_unavailable",
    request_id: "019fe900-6000-7000-8000-000000000003",
    correlation_id: "019fe900-6000-7000-8000-000000000004",
    retryable: true,
  };
  server.use(http.get("*/api/v1/session", () => HttpResponse.json(problem, { status: 503 })));

  renderShell();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Impossible de charger votre session",
  );
  expect(screen.getByRole("button", { name: "Réessayer" })).toBeEnabled();
});

it("keeps the route context visible in the shell empty state", async () => {
  renderShell("/today");

  expect(await screen.findByRole("heading", { level: 1, name: "Aujourd'hui" })).toBeVisible();
  expect(screen.getByText("Aucun contenu disponible")).toBeVisible();
});

it("contains an unexpected render failure in the application error boundary", async () => {
  const user = userEvent.setup();
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);

  function BrokenComponent(): never {
    throw new Error("synthetic shell failure");
  }

  const { reloadApplication } = renderWithErrorBoundary(<BrokenComponent />);

  expect(screen.getByRole("alert")).toHaveTextContent("Une erreur inattendue est survenue");
  await user.click(screen.getByRole("button", { name: "Recharger l'application" }));
  expect(consoleError).toHaveBeenCalled();
  expect(reloadApplication).toHaveBeenCalledOnce();
});
