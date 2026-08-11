import { BookOpenCheck, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useActiveProfile } from "../../app/profile-state";
import type {
  CurrentSessionResponse,
  DueMemoryPromptResponse,
  WordBankItemResponse,
} from "../../generated/model";
import {
  createMemoryPrompt,
  getWordBankOverview,
  listDueMemoryPrompts,
  listMemoryPrompts,
  submitMemoryReview,
} from "../../generated/polyglot";
import { commandFetch, queryFetch, responseProblem } from "../../lib/api";
import { uuid7 } from "../../lib/ids";
import {
  ErrorRegion,
  LoadingRegion,
  StatusPill,
} from "../../components/product-ui";

type Rating = "again" | "hard" | "good" | "easy";

export function DailyVocabulary({
  profileId,
  session,
}: {
  profileId: string;
  session: CurrentSessionResponse;
}) {
  const { activePack } = useActiveProfile();
  const [words, setWords] = useState<WordBankItemResponse[]>([]);
  const [due, setDue] = useState<DueMemoryPromptResponse[]>([]);
  const [promptTargets, setPromptTargets] = useState<Set<string>>(new Set());
  const [revealed, setRevealed] = useState(false);
  const [recalled, setRecalled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [startedAt, setStartedAt] = useState(() => Date.now());

  const refresh = useCallback(async () => {
    const [bankResponse, dueResponse, promptsResponse] = await Promise.all([
      getWordBankOverview(
        profileId,
        { limit: 100 },
        queryFetch(),
      ),
      listDueMemoryPrompts(
        { profile_id: profileId, cutoff: new Date().toISOString(), limit: 100 },
        queryFetch(),
      ),
      listMemoryPrompts(profileId, queryFetch()),
    ]);
    if (bankResponse.status !== 200)
      throw new Error(responseProblem(bankResponse));
    if (dueResponse.status !== 200)
      throw new Error(responseProblem(dueResponse));
    if (promptsResponse.status !== 200)
      throw new Error(responseProblem(promptsResponse));
    setWords(bankResponse.data.items);
    setDue(dueResponse.data.items);
    setPromptTargets(
      new Set(promptsResponse.data.items.map((prompt) => prompt.target_ref)),
    );
  }, [profileId]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void refresh()
        .catch((caught: unknown) => {
          setError(
            caught instanceof Error
              ? caught.message
              : "Le vocabulaire n'est pas disponible.",
          );
        })
        .finally(() => {
          setLoading(false);
        });
    }, 0);
    return () => {
      window.clearTimeout(timeout);
    };
  }, [refresh]);

  const wordBySense = useMemo(
    () => new Map(words.map((word) => [word.sense_id, word])),
    [words],
  );
  const encountered = words.filter(
    (word) => word.encounter_count > 0 && word.sense_revision_id,
  );
  const current = due[0];
  const currentWord = current
    ? wordBySense.get(current.prompt.target_ref)
    : undefined;

  async function prepareCards() {
    setBusy(true);
    setError("");
    try {
      for (const word of encountered) {
        if (!word.sense_revision_id || promptTargets.has(word.sense_id))
          continue;
        const response = await createMemoryPrompt(
          profileId,
          {
            created_at: new Date().toISOString(),
            direction: `${activePack?.target_language_tag ?? "target"}->${activePack?.support_language_tags[0] ?? "support"}`,
            modality: "reading",
            operation: "recall",
            prompt_id: uuid7(),
            protocol_id: "flashcard-recall",
            protocol_revision: 1,
            rating_semantics_id: "fsrs-self-recall-v1",
            scheduler_policy_id: uuid7(),
            target_ref: word.sense_id,
            target_revision_id: word.sense_revision_id,
          },
          commandFetch(session),
        );
        const problem = responseProblem(response);
        if (problem) throw new Error(problem);
      }
      await refresh();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Les cartes n'ont pas pu être préparées.",
      );
    } finally {
      setBusy(false);
    }
  }

  function reveal(didRecall: boolean) {
    setRecalled(didRecall);
    setRevealed(true);
  }

  async function rate(rating: Rating) {
    if (!current) return;
    setBusy(true);
    setError("");
    const now = new Date().toISOString();
    const reviewId = uuid7();
    const response = await submitMemoryReview(
      current.prompt.prompt_id,
      {
        active_duration_ms: Math.min(3_600_000, Date.now() - startedAt),
        answer_revealed: false,
        certification_ref: `self-card:${reviewId}`,
        certified_operation: current.prompt.operation,
        certified_protocol_id: current.prompt.protocol_id,
        certified_protocol_revision: current.prompt.protocol_revision,
        certified_recall: true,
        certified_target_revision_id: current.prompt.target_revision_id,
        exposure_only: false,
        highest_hint: 0,
        incidental_production: false,
        opportunity_id: uuid7(),
        rating,
        review_id: reviewId,
        reviewed_at: now,
        scheduled_at: current.prompt.schedule.due_at,
        self_reported: true,
        verdict: rating === "again" ? "forgotten" : "correct",
      },
      commandFetch(session, current.prompt.version),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      setBusy(false);
      return;
    }
    if (response.status !== 200 || response.data.version <= current.prompt.version) {
      setError("La révision n'a pas produit de nouvelle planification.");
      setBusy(false);
      return;
    }
    setDue((items) => items.slice(1));
    setRevealed(false);
    setRecalled(false);
    setStartedAt(Date.now());
    setBusy(false);
  }

  if (loading)
    return <LoadingRegion label="Préparation du vocabulaire du jour" />;

  return (
    <section
      className="daily-vocabulary"
      aria-labelledby="daily-vocabulary-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Vocabulaire du jour</p>
          <h2 id="daily-vocabulary-title">Réactiver avant la séance</h2>
        </div>
        <StatusPill tone={due.length ? "warn" : "good"}>
          {due.length} à revoir
        </StatusPill>
      </div>
      {error ? <ErrorRegion message={error} /> : null}
      {current ? (
        <div className="memory-card" aria-live="polite">
          <span className="memory-card__counter">
            {due.length} carte{due.length > 1 ? "s" : ""} restante
            {due.length > 1 ? "s" : ""}
          </span>
          <strong lang="it">{currentWord?.label ?? "Mot italien"}</strong>
          {revealed ? (
            <p>{currentWord?.definition ?? "Définition indisponible"}</p>
          ) : (
            <p className="memory-card__prompt">
              Retrouvez le sens en français avant de révéler.
            </p>
          )}
          {!revealed ? (
            <div className="memory-card__actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  reveal(false);
                }}
              >
                <RotateCcw aria-hidden="true" size={17} /> Je ne sais pas
              </button>
              <button
                type="button"
                onClick={() => {
                  reveal(true);
                }}
              >
                Voir la réponse
              </button>
            </div>
          ) : recalled ? (
            <div className="memory-card__actions">
              <button
                disabled={busy}
                className="secondary-button"
                type="button"
                onClick={() => void rate("hard")}
              >
                Difficile
              </button>
              <button
                disabled={busy}
                type="button"
                onClick={() => void rate("good")}
              >
                Bien
              </button>
              <button
                disabled={busy}
                type="button"
                onClick={() => void rate("easy")}
              >
                Facile
              </button>
            </div>
          ) : (
            <button
              disabled={busy}
              type="button"
              onClick={() => void rate("again")}
            >
              <RotateCcw aria-hidden="true" size={17} /> Revoir bientôt
            </button>
          )}
        </div>
      ) : encountered.length ? (
        <div className="memory-card memory-card--complete">
          <BookOpenCheck aria-hidden="true" size={24} />
          <strong>Vos rappels sont à jour</strong>
          <p>Les mots rencontrés restent planifiés par le moteur de mémoire.</p>
          {encountered.some((word) => !promptTargets.has(word.sense_id)) ? (
            <button
              className="secondary-button"
              disabled={busy}
              type="button"
              onClick={() => void prepareCards()}
            >
              {busy ? "Préparation..." : "Préparer mes nouvelles cartes"}
            </button>
          ) : null}
        </div>
      ) : (
        <p className="quiet-copy">
          Le vocabulaire apparaîtra dès l'inscription au premier module.
        </p>
      )}
    </section>
  );
}
