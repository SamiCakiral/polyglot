import {
  ArrowLeft,
  ArrowRight,
  Check,
  Dumbbell,
  FolderOpen,
  RotateCcw,
  SlidersHorizontal,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useActiveProfile } from "../../app/profile-state";
import { useSession } from "../../app/session-context";
import {
  ErrorRegion,
  LoadingRegion,
  NoProfile,
  PageHeader,
  StatusPill,
} from "../../components/product-ui";
import {
  createMemoryPrompt,
  useGetGrammarToolbox,
  listMemoryPrompts,
  prepareSessionPlan,
  startSprintRun,
  submitMemoryReview,
  useAdvancePracticeRun,
  useComposeFreePractice,
  useCreatePracticePreset,
  useGetPracticeRun,
  useListPracticeStacks,
  useStartPracticeRun,
} from "../../generated/polyglot";
import type {
  GrammarRealizationResponse,
  MemoryPromptResponse,
  PracticeDirection,
  PracticeMode,
  PracticeStackResponse,
} from "../../generated/model";
import {
  commandFetch,
  queryFetch,
  responseProblem,
  todayIso,
} from "../../lib/api";
import { freePracticeRunStorageKey } from "../../lib/browser-storage";
import { uuid7 } from "../../lib/ids";
import { focusOptions } from "./practice-focus";

const stackKindLabels: Record<string, string> = {
  daily: "Pile quotidienne",
  list_snapshot: "Liste figée",
  due: "Mots à échéance",
  weak: "Mots fragiles",
  selection: "Sélection personnelle",
  combined: "Piles combinées",
};

function PracticeStackLauncher({
  profileId,
  stack,
}: {
  profileId: string;
  stack: PracticeStackResponse;
}) {
  const session = useSession();
  const navigate = useNavigate();
  const [direction, setDirection] =
    useState<PracticeDirection>("target_to_support");
  const [mode, setMode] = useState<PracticeMode>("cards");
  const [error, setError] = useState("");
  const createPreset = useCreatePracticePreset({
    fetch: commandFetch(session),
  });
  const startRun = useStartPracticeRun({ fetch: commandFetch(session) });

  async function launch() {
    setError("");
    const presetResponse = await createPreset.mutateAsync({
      profileId,
      data: {
        created_at: new Date().toISOString(),
        direction,
        mode,
        name: stack.name,
        settings: { shuffle: false },
        stack_ids: [stack.stack_id],
      },
    });
    const presetProblem = responseProblem(presetResponse);
    if (presetProblem || presetResponse.status !== 201) {
      setError(presetProblem || "La pile n'a pas pu être préparée.");
      return;
    }
    const runResponse = await startRun.mutateAsync({
      presetId: presetResponse.data.preset_id,
      data: { started_at: new Date().toISOString() },
    });
    const runProblem = responseProblem(runResponse);
    if (runProblem || runResponse.status !== 201) {
      setError(runProblem || "L'entraînement n'a pas pu démarrer.");
      return;
    }
    void navigate(`/practice/runs/${runResponse.data.run_id}`);
  }

  return (
    <article className="practice-stack-card">
      <div>
        <FolderOpen aria-hidden="true" size={20} />
        <span>
          <strong>{stack.name}</strong>
          <small>
            {stackKindLabels[stack.stack_kind] ?? stack.stack_kind} ·{" "}
            {stack.members.length} mot{stack.members.length > 1 ? "s" : ""}
          </small>
        </span>
      </div>
      <div className="practice-stack-controls">
        <label>
          Sens
          <select
            value={direction}
            onChange={(event) => {
              setDirection(event.target.value as PracticeDirection);
            }}
          >
            <option value="target_to_support">
              Langue cible → explication
            </option>
            <option value="support_to_target">
              Explication → langue cible
            </option>
            <option value="bidirectional">Les deux sens</option>
          </select>
        </label>
        <label>
          Mode
          <select
            value={mode}
            onChange={(event) => {
              setMode(event.target.value as PracticeMode);
            }}
          >
            <option value="cards">Cartes recto-verso</option>
            <option value="recognition">Reconnaissance</option>
            <option value="recall">Rappel actif</option>
            <option value="mixed">Mixte</option>
          </select>
        </label>
      </div>
      {error ? <ErrorRegion message={error} /> : null}
      <button
        disabled={createPreset.isPending || startRun.isPending}
        type="button"
        onClick={() => void launch()}
      >
        Entraîner cette pile <ArrowRight aria-hidden="true" size={18} />
      </button>
    </article>
  );
}

export function PracticePage() {
  const { activePack, activeProfile } = useActiveProfile();
  const session = useSession();
  const navigate = useNavigate();
  const [workspace, setWorkspace] = useState<"stacks" | "grammar" | "free">(
    "stacks",
  );
  const [grammarFamily, setGrammarFamily] = useState("priority_productive");
  const [focus, setFocus] = useState<(typeof focusOptions)[number]>(
    focusOptions[0],
  );
  const [budget, setBudget] = useState(20);
  const [challenge, setChallenge] = useState("matched");
  const [error, setError] = useState("");
  const compose = useComposeFreePractice({ fetch: commandFetch(session) });
  const profileId = activeProfile?.profile_id ?? "";
  const stacksQuery = useListPracticeStacks(profileId, {
    fetch: queryFetch(),
    query: { enabled: Boolean(activeProfile), retry: false },
  });
  const grammarQuery = useGetGrammarToolbox(
    activePack?.pack_revision_id ?? "",
    { support_language_tag: activePack?.support_language_tags[0] ?? "fr-FR" },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activePack), retry: false },
    },
  );
  const activeRunKey = freePracticeRunStorageKey(session.account_id, profileId);
  const activeRunId = localStorage.getItem(activeRunKey);

  if (!activeProfile) return <NoProfile />;
  const stacks =
    stacksQuery.data?.status === 200 ? stacksQuery.data.data.items : [];
  const grammarToolbox =
    grammarQuery.data?.status === 200 ? grammarQuery.data.data : null;

  async function launchFreePractice(grammar?: GrammarRealizationResponse) {
    setError("");
    const planId = uuid7();
    const response = await compose.mutateAsync({
      profileId,
      data: {
        allow_novelty: false,
        budget_minutes: budget,
        challenge,
        modalities: grammar ? ["reading", "writing"] : [...focus.modalities],
        pedagogical_day: todayIso(),
        plan_id: planId,
        primitive_ids: grammar
          ? ["EX-EXPOSE-01", "EX-RECALL-02", "EX-TRANSFORM-01"]
          : [...focus.primitives],
        snapshot_id: uuid7(),
        target_refs: [
          grammar ? `grammar:${grammar.realization_code}` : focus.target,
        ],
      },
    });
    const problem = responseProblem(response);
    if (problem || response.status !== 201) {
      setError(problem || "La séance n'a pas pu être composée.");
      return;
    }
    const prepared = await prepareSessionPlan(
      planId,
      {},
      commandFetch(session, response.data.version),
    );
    const prepareProblem = responseProblem(prepared);
    if (prepareProblem) {
      setError(prepareProblem);
      return;
    }
    const runId = uuid7();
    const started = await startSprintRun(
      planId,
      { run_id: runId },
      commandFetch(session),
    );
    const startProblem = responseProblem(started);
    if (startProblem) {
      setError(startProblem);
      return;
    }
    localStorage.setItem(activeRunKey, runId);
    void navigate(`/sprints/${runId}`);
  }

  return (
    <div className="page-flow">
      <PageHeader
        eyebrow="Hors curriculum"
        title="S'entraîner"
        description="Rejouez vos piles exactes ou ciblez une compétence sans déplacer votre séance quotidienne."
        action={<SlidersHorizontal aria-hidden="true" />}
      />
      <div
        className="segmented-control practice-workspace-tabs"
        role="tablist"
        aria-label="Type d'entraînement"
      >
        <button
          className="segment"
          aria-selected={workspace === "stacks"}
          role="tab"
          type="button"
          onClick={() => {
            setWorkspace("stacks");
          }}
        >
          <FolderOpen aria-hidden="true" size={17} /> Mes piles
        </button>
        <button
          className="segment"
          aria-selected={workspace === "grammar"}
          role="tab"
          type="button"
          onClick={() => {
            setWorkspace("grammar");
          }}
        >
          <Dumbbell aria-hidden="true" size={17} /> Boîte grammaticale
        </button>
        <button
          className="segment"
          aria-selected={workspace === "free"}
          role="tab"
          type="button"
          onClick={() => {
            setWorkspace("free");
          }}
        >
          <Dumbbell aria-hidden="true" size={17} /> Entraînement libre
        </button>
      </div>
      {workspace === "stacks" ? (
        <section className="practice-stack-library">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Mémoire personnelle</p>
              <h2>Piles disponibles</h2>
            </div>
            <StatusPill>{stacks.length}</StatusPill>
          </div>
          {stacksQuery.isPending ? (
            <LoadingRegion label="Ouverture de vos piles" />
          ) : stacks.length ? (
            <div className="practice-stack-grid">
              {stacks.map((stack) => (
                <PracticeStackLauncher
                  key={stack.stack_id}
                  profileId={profileId}
                  stack={stack}
                />
              ))}
            </div>
          ) : (
            <div className="empty-panel">
              <FolderOpen aria-hidden="true" />
              <h2>Aucune pile enregistrée</h2>
              <p>
                Sélectionnez des mots dans votre vocabulaire pour créer votre
                première pile.
              </p>
              <Link className="button-link" to="/vocabulary">
                Ouvrir le vocabulaire{" "}
                <ArrowRight aria-hidden="true" size={17} />
              </Link>
            </div>
          )}
        </section>
      ) : workspace === "grammar" ? (
        <section className="grammar-toolbox">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Fonction → moule</p>
              <h2>Boîte grammaticale</h2>
            </div>
            <StatusPill>{grammarToolbox?.realizations.length ?? 0}</StatusPill>
          </div>
          {grammarQuery.isPending ? (
            <LoadingRegion label="Ouverture de la boîte grammaticale" />
          ) : !grammarToolbox ? (
            <ErrorRegion message="La boîte grammaticale n'est pas encore disponible pour ce profil." />
          ) : (
            <>
              <label className="grammar-family-filter">
                Famille
                <select
                  value={grammarFamily}
                  onChange={(event) => {
                    setGrammarFamily(event.target.value);
                  }}
                >
                  {grammarToolbox.families.map((family) => (
                    <option key={family.code} value={family.code}>
                      {family.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grammar-realization-list">
                {grammarToolbox.realizations
                  .filter(
                    (item) =>
                      grammarFamily === "priority_productive" ||
                      item.family_code === grammarFamily,
                  )
                  .map((item) => (
                    <article key={item.realization_code}>
                      <div>
                        <p>{item.support_template}</p>
                        <h3 lang={grammarToolbox.target_language_tag}>
                          {item.target_template}
                        </h3>
                        <small lang={grammarToolbox.target_language_tag}>
                          {item.examples[0]}
                        </small>
                      </div>
                      <button
                        disabled={compose.isPending}
                        type="button"
                        onClick={() => void launchFreePractice(item)}
                      >
                        Étudier puis transformer
                        <ArrowRight aria-hidden="true" size={17} />
                      </button>
                    </article>
                  ))}
              </div>
            </>
          )}
          {error ? <ErrorRegion message={error} /> : null}
        </section>
      ) : (
        <section className="practice-configurator">
          <div>
            <p className="eyebrow">Cible</p>
            <h2>Que voulez-vous travailler ?</h2>
            <div className="choice-stack">
              {focusOptions.map((option) => (
                <button
                  aria-pressed={focus.id === option.id}
                  className="practice-choice"
                  key={option.id}
                  type="button"
                  onClick={() => {
                    setFocus(option);
                  }}
                >
                  <Dumbbell aria-hidden="true" size={20} />
                  <span>
                    {option.label}
                    <small>{option.description}</small>
                  </span>
                </button>
              ))}
            </div>
          </div>
          <div className="practice-options">
            <label>
              Durée
              <select
                value={budget}
                onChange={(event) => {
                  setBudget(Number(event.target.value));
                }}
              >
                <option value={10}>10 minutes</option>
                <option value={20}>20 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={45}>45 minutes</option>
              </select>
            </label>
            <label>
              Difficulté
              <select
                value={challenge}
                onChange={(event) => {
                  setChallenge(event.target.value);
                }}
              >
                <option value="gentler">Guidée</option>
                <option value="matched">Équilibrée</option>
                <option value="stretch">Exigeante</option>
              </select>
            </label>
            <p>
              Cette séance travaille uniquement des cibles déjà rencontrées.
            </p>
            {error ? <ErrorRegion message={error} /> : null}
            {activeRunId ? (
              <button
                type="button"
                onClick={() => void navigate(`/sprints/${activeRunId}`)}
              >
                Reprendre la séance en cours{" "}
                <ArrowRight aria-hidden="true" size={18} />
              </button>
            ) : (
              <button
                disabled={compose.isPending}
                type="button"
                onClick={() => void launchFreePractice()}
              >
                Lancer l'entraînement{" "}
                <ArrowRight aria-hidden="true" size={18} />
              </button>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

export function PracticeRunPage() {
  const { practiceRunId = "" } = useParams();
  const { activePack } = useActiveProfile();
  const session = useSession();
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState("");
  const [startedAt, setStartedAt] = useState(() => Date.now());
  const [ratingPending, setRatingPending] = useState(false);
  const query = useGetPracticeRun(practiceRunId, {
    fetch: queryFetch(),
    query: { enabled: Boolean(practiceRunId), retry: false },
  });
  const run = query.data?.status === 200 ? query.data.data : null;
  const advance = useAdvancePracticeRun({
    fetch: commandFetch(session, run?.version),
  });

  if (query.isPending) return <LoadingRegion label="Ouverture de la pile" />;
  if (!run)
    return (
      <ErrorRegion message="Cette session d'entraînement n'est pas disponible." />
    );
  if (run.status === "completed") {
    return (
      <div className="practice-run-shell">
        <section className="practice-run-complete">
          <Check aria-hidden="true" size={28} />
          <p className="eyebrow">Pile terminée</p>
          <h1>
            {run.member_count}{" "}
            {run.member_count === 1 ? "carte parcourue" : "cartes parcourues"}
          </h1>
          <p>Cette lecture n'attribue pas de maîtrise sans réponse corrigée.</p>
          <Link className="button-link" to="/practice">
            Revenir aux entraînements{" "}
            <ArrowRight aria-hidden="true" size={17} />
          </Link>
        </section>
      </div>
    );
  }
  const item = run.current_item;
  if (!item)
    return <ErrorRegion message="La prochaine carte est indisponible." />;
  const activeRun = run;
  const currentItem = item;
  const reverse =
    run.direction === "support_to_target" ||
    (run.direction === "bidirectional" && run.current_position % 2 === 1);
  const front = reverse ? item.definition : item.label;
  const back = reverse ? item.label : item.definition;
  const targetLanguage = activePack?.target_language_tag ?? "und";

  async function ensurePrompt(
    direction: string,
    operation: string,
  ): Promise<MemoryPromptResponse> {
    const promptsResponse = await listMemoryPrompts(
      activeRun.profile_id,
      queryFetch(),
    );
    const promptsProblem = responseProblem(promptsResponse);
    if (promptsProblem || promptsResponse.status !== 200) {
      throw new Error(promptsProblem || "Les rappels ne sont pas disponibles.");
    }
    const existing = promptsResponse.data.items.find(
      (prompt) =>
        prompt.target_ref === currentItem.sense_id &&
        prompt.target_revision_id === currentItem.sense_revision_id &&
        prompt.direction === direction &&
        prompt.operation === operation &&
        prompt.status === "active",
    );
    if (existing) return existing;

    const promptResponse = await createMemoryPrompt(
      activeRun.profile_id,
      {
        created_at: new Date().toISOString(),
        direction,
        modality: "reading",
        operation,
        prompt_id: uuid7(),
        protocol_id: "practice-stack-self-recall",
        protocol_revision: 1,
        rating_semantics_id: "fsrs-self-recall-v1",
        scheduler_policy_id: uuid7(),
        target_ref: currentItem.sense_id,
        target_revision_id: currentItem.sense_revision_id,
      },
      commandFetch(session),
    );
    const promptProblem = responseProblem(promptResponse);
    if (promptProblem || promptResponse.status !== 201) {
      throw new Error(promptProblem || "Le rappel n'a pas pu être créé.");
    }
    return promptResponse.data;
  }

  async function rate(rating: "again" | "hard" | "good" | "easy") {
    setError("");
    setRatingPending(true);
    try {
      const targetTag = activePack?.target_language_tag ?? "target";
      const supportTag = activePack?.support_language_tags[0] ?? "support";
      const direction = reverse
        ? `${supportTag}->${targetTag}`
        : `${targetTag}->${supportTag}`;
      const operation = reverse ? "recall" : "recognition";
      const prompt = await ensurePrompt(direction, operation);
      const now = new Date().toISOString();
      const nowMs = Date.parse(now);
      const reviewId = uuid7();
      const reviewResponse = await submitMemoryReview(
        prompt.prompt_id,
        {
          active_duration_ms: Math.min(3_600_000, nowMs - startedAt),
          answer_revealed: false,
          certification_ref: `practice-run:${practiceRunId}:${reviewId}`,
          certified_operation: prompt.operation,
          certified_protocol_id: prompt.protocol_id,
          certified_protocol_revision: prompt.protocol_revision,
          certified_recall: true,
          certified_target_revision_id: prompt.target_revision_id,
          exposure_only: false,
          highest_hint: 0,
          incidental_production: false,
          opportunity_id: uuid7(),
          rating,
          review_id: reviewId,
          reviewed_at: now,
          scheduled_at: prompt.schedule.due_at,
          self_reported: true,
          verdict: rating === "again" ? "forgotten" : "correct",
        },
        commandFetch(session, prompt.version),
      );
      const reviewProblem = responseProblem(reviewResponse);
      if (reviewProblem || reviewResponse.status !== 200) {
        throw new Error(
          reviewProblem || "La révision n'a pas pu être enregistrée.",
        );
      }
      if (reviewResponse.data.version <= prompt.version) {
        throw new Error(
          "La révision n'a pas produit de nouvelle planification.",
        );
      }
      const response = await advance.mutateAsync({
        runId: practiceRunId,
        data: { at: now },
      });
      const problem = responseProblem(response);
      if (problem) throw new Error(problem);
      setRevealed(false);
      setStartedAt(nowMs);
      await query.refetch();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "La carte n'a pas pu être enregistrée.",
      );
    } finally {
      setRatingPending(false);
    }
  }

  return (
    <main className="practice-run-shell">
      <header className="practice-run-header">
        <Link
          aria-label="Quitter la pile"
          className="icon-button"
          to="/practice"
        >
          <ArrowLeft aria-hidden="true" />
        </Link>
        <span>
          {run.current_position + 1} / {run.member_count}
        </span>
      </header>
      <section className="practice-flashcard" aria-live="polite">
        <p className="eyebrow">
          {reverse ? "Retrouvez le mot" : "Retrouvez le sens"}
        </p>
        <h1 lang={reverse ? undefined : targetLanguage}>{front}</h1>
        {revealed ? (
          <div className="practice-flashcard__answer">
            <span>Réponse</span>
            <strong lang={reverse ? targetLanguage : undefined}>{back}</strong>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => {
              setRevealed(true);
            }}
          >
            Retourner la carte <RotateCcw aria-hidden="true" size={18} />
          </button>
        )}
      </section>
      {error ? <ErrorRegion message={error} /> : null}
      {revealed ? (
        <div className="practice-rating-grid" aria-label="Évaluer le rappel">
          {(
            [
              ["again", "À revoir"],
              ["hard", "Difficile"],
              ["good", "Correct"],
              ["easy", "Facile"],
            ] as const
          ).map(([value, label]) => (
            <button
              className={`practice-rating practice-rating--${value}`}
              disabled={ratingPending || advance.isPending}
              key={value}
              type="button"
              onClick={() => void rate(value)}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}
    </main>
  );
}
