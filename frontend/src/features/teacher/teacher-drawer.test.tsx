import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { server } from "../../../tests/support/server";
import { renderShell } from "../../shell/test-utils";

const profileId = "019fe900-6000-7000-8000-000000000010";
const conversationId = "019fe900-6000-7000-8000-000000000020";
const actionId = "019fe900-6000-7000-8000-000000000030";

function useLanguageContext(): void {
  server.use(
    http.get("*/api/v1/language-profiles", () =>
      HttpResponse.json({
        items: [
          {
            account_id: "019fe900-6000-7000-8000-000000000001",
            archived_at: null,
            created_at: "2026-08-11T08:00:00Z",
            current_phase: "active",
            deleted_at: null,
            excluded_themes: [],
            goals: [],
            interests: [],
            native_variety_id: "019b0000-0000-7000-8000-000000000005",
            profile_id: profileId,
            status: "active",
            target_variety_id: "019b0000-0000-7000-8000-000000000002",
            updated_at: "2026-08-11T08:00:00Z",
            version: 1,
          },
        ],
      }),
    ),
    http.get("*/api/v1/language-packs", () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get("*/api/v1/account-languages", () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

function conversation(status: "applied" | "reverted" = "applied") {
  return {
    conversation_id: conversationId,
    created_at: "2026-08-11T08:00:00Z",
    messages: [
      {
        actions: [],
        content: "Aide-moi à retravailler vorrei.",
        created_at: "2026-08-11T08:01:00Z",
        message_id: "019fe900-6000-7000-8000-000000000021",
        model_code: null,
        provider_code: null,
        role: "user",
      },
      {
        actions: [
          {
            action_id: actionId,
            action_type: "create_learning_debt",
            applied_at: "2026-08-11T08:01:01Z",
            payload: { note: "Différence entre vorrei et voglio" },
            reverted_at: status === "reverted" ? "2026-08-11T08:02:00Z" : null,
            status,
            version: status === "reverted" ? 2 : 1,
          },
        ],
        content: "Je l’ajoute aux points à retravailler.",
        created_at: "2026-08-11T08:01:01Z",
        message_id: "019fe900-6000-7000-8000-000000000022",
        model_code: "qwen/qwen3.6-35b-a3b",
        provider_code: "lmstudio",
        role: "assistant",
      },
    ],
    profile_id: profileId,
    status: "active",
    title: "Questions au professeur",
    updated_at: "2026-08-11T08:01:01Z",
    version: 3,
  };
}

afterEach(cleanup);

describe("profile-aware teacher", () => {
  it("stays unavailable until a learning profile is selected", async () => {
    renderShell("/today");

    expect(
      await screen.findByRole("button", { name: "Ouvrir le professeur" }),
    ).toBeDisabled();
  });

  it("shows the immutable history and compensates a reversible action", async () => {
    useLanguageContext();
    let reverted = false;
    server.use(
      http.get("*/api/v1/language-profiles/:profileId/teacher-conversations", () =>
        HttpResponse.json({ items: [conversation()], next_cursor: null }),
      ),
      http.post(/\/api\/v1\/teacher-actions\/[^/]+:revert$/, () => {
        reverted = true;
        return HttpResponse.json({
          ...conversation("reverted").messages[1]?.actions[0],
        });
      }),
      http.get("*/api/v1/teacher-conversations/:conversationId", () =>
        HttpResponse.json(conversation(reverted ? "reverted" : "applied")),
      ),
    );

    const user = userEvent.setup();
    renderShell("/practice");
    await user.click(
      await screen.findByRole("button", { name: "Ouvrir le professeur" }),
    );

    expect(await screen.findByText("Je l’ajoute aux points à retravailler.")).toBeVisible();
    expect(screen.getByText("Point à retravailler créé")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Annuler cette action" }));

    await waitFor(() => {
      expect(reverted).toBe(true);
      expect(screen.getByText("Annulée")).toBeVisible();
    });
    expect(screen.getByText("Aide-moi à retravailler vorrei.")).toBeVisible();
  });

  it("resynchronizes an accepted message after an invalid local response", async () => {
    useLanguageContext();
    const emptyConversation = { ...conversation(), messages: [], version: 1 };
    const acceptedConversation = {
      ...emptyConversation,
      messages: [
        {
          actions: [],
          content: "Explique-moi vorrei.",
          created_at: "2026-08-11T08:03:00Z",
          message_id: "019fe900-6000-7000-8000-000000000024",
          model_code: null,
          provider_code: null,
          role: "user",
        },
      ],
      version: 2,
    };
    server.use(
      http.get("*/api/v1/language-profiles/:profileId/teacher-conversations", () =>
        HttpResponse.json({ items: [emptyConversation], next_cursor: null }),
      ),
      http.post("*/api/v1/teacher-conversations/:conversationId/messages", () =>
        HttpResponse.json({ detail: "Tool schema invalid" }, { status: 409 }),
      ),
      http.get("*/api/v1/teacher-conversations/:conversationId", () =>
        HttpResponse.json(acceptedConversation),
      ),
    );

    const user = userEvent.setup();
    renderShell("/today");
    await user.click(
      await screen.findByRole("button", { name: "Ouvrir le professeur" }),
    );
    const question = screen.getByRole("textbox", { name: "Question au professeur" });
    await user.type(question, "Explique-moi vorrei.");
    await user.click(screen.getByRole("button", { name: "Envoyer la question" }));

    expect(
      await screen.findByText(
        "La réponse locale était incomplète ou mal formée. Elle n’a pas été rejouée.",
      ),
    ).toBeVisible();
    expect(screen.getByText("Explique-moi vorrei.")).toBeVisible();
    expect(question).toHaveValue("");
  });
});
