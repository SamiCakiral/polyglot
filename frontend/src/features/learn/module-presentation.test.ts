import { describe, expect, it } from "vitest";

import { modulePresentation } from "./module-presentation";

describe("modulePresentation", () => {
  it("gives the Italian pilot an editorial learner-facing title", () => {
    expect(
      modulePresentation(
        "IT-FIRST-AUTONOMOUS-EXCHANGE",
        "entrer en contact, obtenir quelque chose et reparer un echange",
      ),
    ).toEqual({
      description:
        "Entrer en contact, obtenir quelque chose et réparer un échange simple.",
      title: "Premiers échanges autonomes",
    });
  });

  it("uses the editorial intention for future modules", () => {
    expect(modulePresentation("FUTURE_MODULE", "prendre le train")).toEqual({
      description: "Prendre le train.",
      title: "Prendre le train",
    });
  });
});
