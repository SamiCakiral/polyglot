import { ArrowRight, BookOpen, RotateCcw, X } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { useLocation } from "react-router-dom";

import { useActiveProfile } from "../../app/profile-state";
import { useSession } from "../../app/session-context";
import type {
  TeacherActionResponse,
  TeacherConversationResponse,
} from "../../generated/model";
import {
  createTeacherConversation,
  getTeacherConversation,
  revertTeacherAction,
  sendTeacherMessage,
  useListTeacherConversations,
} from "../../generated/polyglot";
import { commandFetch, queryFetch, responseProblem } from "../../lib/api";
import { uuid7 } from "../../lib/ids";

const actionLabels: Record<string, string> = {
  add_word_to_list: "Mot ajouté à une liste",
  create_learning_debt: "Point à retravailler créé",
  prepare_exercise: "Exercice préparé",
  create_practice_preset: "Entraînement préparé",
  record_encounter: "Rencontre lexicale enregistrée",
};

function ActionRow({
  action,
  onRevert,
}: {
  action: TeacherActionResponse;
  onRevert: (action: TeacherActionResponse) => void;
}) {
  return (
    <div className="teacher-action">
      <span>{actionLabels[action.action_type] ?? action.action_type}</span>
      {action.status === "applied" ? (
        <button
          aria-label="Annuler cette action"
          className="icon-button teacher-action__undo"
          title="Annuler cette action"
          type="button"
          onClick={() => {
            onRevert(action);
          }}
        >
          <RotateCcw aria-hidden="true" size={16} />
        </button>
      ) : (
        <small>Annulée</small>
      )}
    </div>
  );
}

export function TeacherDrawer() {
  const { activeProfile } = useActiveProfile();
  const session = useSession();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [conversation, setConversation] =
    useState<TeacherConversationResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const profileId = activeProfile?.profile_id ?? "";
  const conversationsQuery = useListTeacherConversations(profileId, {
    fetch: queryFetch(),
    query: { enabled: open && Boolean(profileId), retry: false },
  });
  const listed =
    conversationsQuery.data?.status === 200
      ? conversationsQuery.data.data.items
      : [];
  const activeConversation =
    conversation?.profile_id === profileId ? conversation : listed[0] ?? null;

  async function ensureConversation() {
    if (activeConversation) return activeConversation;
    const response = await createTeacherConversation(
      profileId,
      { conversation_id: uuid7(), title: "Questions au professeur" },
      commandFetch(session),
    );
    const problem = responseProblem(response);
    if (problem || response.status !== 201) {
      throw new Error(problem || "Le professeur n'a pas pu ouvrir la conversation.");
    }
    return response.data;
  }

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || !activeProfile || pending) return;
    setPending(true);
    setError("");
    let current: TeacherConversationResponse | null = null;
    try {
      current = await ensureConversation();
      setConversation(current);
      const response = await sendTeacherMessage(
        current.conversation_id,
        {
          content,
          message_id: uuid7(),
          page_context: {
            route: location.pathname,
            page_title: document.title,
          },
        },
        commandFetch(session, current.version),
      );
      const problem = responseProblem(response);
      if (problem || response.status !== 201) {
        throw new Error(problem || "Le professeur local est indisponible.");
      }
      setConversation(response.data);
      setDraft("");
    } catch (caught) {
      if (current) {
        const refreshed = await getTeacherConversation(
          current.conversation_id,
          queryFetch(),
        );
        if (refreshed.status === 200) {
          setConversation(refreshed.data);
          const latest = refreshed.data.messages.at(-1);
          if (latest?.role === "user" && latest.content === content) setDraft("");
        }
      }
      const message = caught instanceof Error ? caught.message : "";
      setError(
        message === "Tool schema invalid"
          ? "La réponse locale était incomplète ou mal formée. Elle n’a pas été rejouée."
          : message || "Le professeur local est indisponible.",
      );
    } finally {
      setPending(false);
    }
  }

  async function undo(action: TeacherActionResponse) {
    if (!activeConversation) return;
    setError("");
    const response = await revertTeacherAction(
      action.action_id,
      commandFetch(session, action.version),
    );
    const problem = responseProblem(response);
    if (problem || response.status !== 200) {
      setError(problem || "Cette action n'a pas pu être annulée.");
      return;
    }
    const refreshed = await getTeacherConversation(
      activeConversation.conversation_id,
      queryFetch(),
    );
    if (refreshed.status === 200) setConversation(refreshed.data);
  }

  return (
    <>
      {!open ? (
        <button
          aria-label="Ouvrir le professeur"
          className="teacher-launcher"
          disabled={!activeProfile}
          title={activeProfile ? "Professeur" : "Choisissez d'abord une langue"}
          type="button"
          onClick={() => {
            setOpen(true);
          }}
        >
          <BookOpen aria-hidden="true" size={23} />
        </button>
      ) : null}
      {open ? (
        <aside aria-label="Professeur" className="teacher-drawer">
          <header className="teacher-drawer__header">
            <div>
              <span className="eyebrow">Profil actif</span>
              <strong>Professeur</strong>
            </div>
            <button
              aria-label="Fermer le professeur"
              className="icon-button"
              type="button"
              onClick={() => {
                setOpen(false);
              }}
            >
              <X aria-hidden="true" size={20} />
            </button>
          </header>
          <div aria-live="polite" className="teacher-messages">
            {activeConversation?.messages.length ? (
              activeConversation.messages.map((message) => (
                <div
                  className={`teacher-message teacher-message--${message.role}`}
                  key={message.message_id}
                >
                  <span>{message.role === "user" ? "Vous" : "Professeur"}</span>
                  <p>{message.content}</p>
                  {message.actions.map((action) => (
                    <ActionRow
                      action={action}
                      key={action.action_id}
                      onRevert={(selectedAction) => {
                        void undo(selectedAction);
                      }}
                    />
                  ))}
                </div>
              ))
            ) : (
              <p className="teacher-empty">Posez votre question sur la séance en cours.</p>
            )}
            {pending ? <p className="teacher-thinking">Le professeur répond…</p> : null}
          </div>
          {error ? <p className="teacher-error" role="alert">{error}</p> : null}
          <form
            className="teacher-composer"
            onSubmit={(event) => {
              void submit(event);
            }}
          >
            <label className="sr-only" htmlFor="teacher-question">
              Question au professeur
            </label>
            <textarea
              id="teacher-question"
              maxLength={6000}
              placeholder="Votre question"
              rows={3}
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
              }}
            />
            <button
              aria-label="Envoyer la question"
              className="icon-button"
              disabled={!draft.trim() || pending}
              title="Envoyer"
              type="submit"
            >
              <ArrowRight aria-hidden="true" size={19} />
            </button>
          </form>
        </aside>
      ) : null}
    </>
  );
}
