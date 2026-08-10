import { screen } from "@testing-library/react";
import axe from "axe-core";
import { expect, it } from "vitest";

import { renderShell } from "./test-utils";

it("has no serious or critical axe violation in the ready shell", async () => {
  const { container } = renderShell();

  await screen.findByRole("heading", { level: 1, name: "Aujourd'hui" });
  const result = await axe.run(container);
  const blockingViolations = result.violations.filter(
    ({ impact }) => impact === "serious" || impact === "critical",
  );

  expect(blockingViolations).toEqual([]);
});
