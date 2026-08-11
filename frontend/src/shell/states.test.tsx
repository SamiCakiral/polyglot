import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http } from "msw";
import { expect, it } from "vitest";

import type { ProblemResponse } from "../generated/model";
import { server } from "../../tests/support/server";
import { renderShell, renderWithErrorBoundary } from "./test-utils";

function problemResponse(
  status: number,
  code: string,
  retryable: boolean,
): ProblemResponse {
  return {
    type: "about:blank",
    title: code,
    status,
    detail: `Synthetic ${code} response.`,
    instance: "/api/v1/session",
    code,
    message_key: `errors.${code}`,
    request_id: "019fe900-6000-7000-8000-000000000003",
    correlation_id: "019fe900-6000-7000-8000-000000000004",
    retryable,
  };
}

function useSessionProblem(status: number, code: string, retryable: boolean): void {
  server.use(
    http.get("*/api/v1/session", () =>
      HttpResponse.json(problemResponse(status, code, retryable), { status }),
    ),
  );
}

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

it("sends an unauthenticated session to the reconnection path without retry", async () => {
  useSessionProblem(401, "unauthenticated", false);

  renderShell();

  expect(await screen.findByRole("alert")).toHaveTextContent("Votre session a expiré");
  expect(screen.getByRole("link", { name: "Se reconnecter" })).toHaveAttribute(
    "href",
    "/login",
  );
  expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
});

it("sends a forbidden session to a safe destination without retry", async () => {
  useSessionProblem(403, "forbidden", false);

  renderShell();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Vous n'avez pas accès à cette page",
  );
  expect(screen.getByRole("link", { name: "Revenir à la connexion" })).toHaveAttribute(
    "href",
    "/login",
  );
  expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
});

it("does not offer retry when the API marks a session failure as non-retryable", async () => {
  useSessionProblem(423, "account_locked", false);

  renderShell();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Votre session ne peut pas être ouverte",
  );
  expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
});

it("offers a manual retry for a retryable rate limit", async () => {
  useSessionProblem(429, "rate_limited", true);

  renderShell();

  expect(await screen.findByRole("alert")).toHaveTextContent("Trop de demandes");
  expect(screen.getByRole("button", { name: "Réessayer" })).toBeEnabled();
});

it("offers a manual retry for a retryable dependency failure", async () => {
  useSessionProblem(503, "dependency_unavailable", true);

  renderShell();

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Service temporairement indisponible",
  );
  expect(screen.getByRole("button", { name: "Réessayer" })).toBeEnabled();
});

it("offers a manual retry after a transport failure", async () => {
  server.use(http.get("*/api/v1/session", () => HttpResponse.error()));

  renderShell();

  expect(await screen.findByRole("alert")).toHaveTextContent("Connexion interrompue");
  expect(screen.getByRole("button", { name: "Réessayer" })).toBeEnabled();
});

it("keeps the route context visible while product data loads", async () => {
  renderShell("/today");

  expect(await screen.findByRole("heading", { level: 1, name: "Aujourd'hui" })).toBeVisible();
  expect(screen.getByText("Séance du jour")).toBeVisible();
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
