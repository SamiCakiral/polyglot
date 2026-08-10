import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import shellFixture from "../../../fixtures/canonical/FX-UI/shell.json";
import { renderShell } from "./test-utils";

afterEach(() => {
  cleanup();
});

describe("W17-T01 structural routes", () => {
  it.each(shellFixture.routes)("keeps %s accessible inside the application shell", async (path) => {
    renderShell(path);

    const heading = await screen.findByRole("heading", { level: 1 });
    const main = heading.closest("main");
    if (!main) {
      throw new Error(`Missing main landmark for ${path}`);
    }
    expect(heading).toBeVisible();
    expect(within(main).queryByText("Page introuvable")).not.toBeInTheDocument();
  });

  it("exposes the six desktop destinations in canonical order", async () => {
    renderShell();

    const navigation = await screen.findByRole("navigation", {
      name: "Navigation principale",
    });
    const labels = within(navigation)
      .getAllByRole("link")
      .map((link) => link.textContent.trim());

    expect(labels).toEqual([
      "Aujourd'hui",
      "Apprendre",
      "S'entraîner",
      "Vocabulaire",
      "Progression",
      "Évaluer",
    ]);
  });

  it("navigates with the keyboard and announces the active destination", async () => {
    const user = userEvent.setup();
    renderShell();

    const navigation = await screen.findByRole("navigation", {
      name: "Navigation principale",
    });
    const learnLink = within(navigation).getByRole("link", { name: "Apprendre" });
    learnLink.focus();
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("heading", { level: 1, name: "Apprendre" })).toBeVisible();
    expect(learnLink).toHaveAttribute("aria-current", "page");
  });

  it("moves focus to main content through the skip link", async () => {
    const user = userEvent.setup();
    renderShell();

    await screen.findByRole("heading", { level: 1, name: "Aujourd'hui" });
    await user.tab();
    const skipLink = screen.getByRole("link", { name: "Aller au contenu principal" });
    expect(skipLink).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(screen.getByRole("main")).toHaveFocus();
  });
});
