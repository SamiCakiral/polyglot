import { ArrowLeft, ArrowRight, Headphones, Pause } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useSession } from "../../app/session-context";
import { useActiveProfile } from "../../app/profile-state";
import { ErrorRegion, LoadingRegion } from "../../components/product-ui";
import { TtsAudio } from "../../components/tts-audio";
import type {
  AnswerKind,
  JsonValueInput,
  SprintBlockResponse,
} from "../../generated/model";
import {
  completeSprintRun,
  evaluateExerciseAttempt,
  interruptSprintRun,
  submitExerciseAttempt,
  useGetAttempt,
  useGetExerciseInstance,
  useGetSprintRun,
  useOpenExerciseAttempt,
} from "../../generated/polyglot";
import { commandFetch, queryFetch, responseProblem } from "../../lib/api";
import {
  activeRunStorageKey,
  freePracticeRunStorageKey,
} from "../../lib/browser-storage";
import { uuid7 } from "../../lib/ids";
import { PrimitiveResponseEditor } from "../exercises/primitive-response-editor";
import {
  isResponseComplete,
  normalizeResponse,
  type PrimitiveResponse,
} from "../exercises/primitive-response";
import { resumeBlockOffset } from "./sprint-position";
import { sprintFamilyLabel } from "./sprint-family-label";

function readableBinding(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  for (const key of [
    "prompt",
    "text",
    "sentence",
    "surface",
    "label",
    "instruction",
    "source",
  ]) {
    if (typeof record[key] === "string") return record[key];
  }
  return null;
}

function storedResponse(key: string): PrimitiveResponse {
  const stored = localStorage.getItem(key);
  if (stored === null) return "";
  try {
    return JSON.parse(stored) as PrimitiveResponse;
  } catch {
    return stored;
  }
}

function responseLabel(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "Activité effectuée";
  return JSON.stringify(value);
}

function ExerciseReader({
  instanceId,
  onDone,
}: {
  instanceId: string;
  onDone: () => void;
}) {
  const session = useSession();
  const { activePack, activeProfile } = useActiveProfile();
  const targetLanguageTag = activePack?.target_language_tag ?? "und";
  const query = useGetExerciseInstance(instanceId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const attemptStorageKey = `polyglot.attempt.${instanceId}`;
  const [attemptId] = useState(() => {
    const stored = localStorage.getItem(attemptStorageKey);
    if (stored) return stored;
    const created = uuid7();
    localStorage.setItem(attemptStorageKey, created);
    return created;
  });
  const attemptQuery = useGetAttempt(attemptId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const [attemptVersion, setAttemptVersion] = useState<number | null>(null);
  const storageKey = `polyglot.draft.${instanceId}`;
  const [answer, setAnswer] = useState<PrimitiveResponse>(() =>
    storedResponse(storageKey),
  );
  const [opened, setOpened] = useState(false);
  const [submittedVersion, setSubmittedVersion] = useState<number | null>(null);
  const [error, setError] = useState("");
  const openAttempt = useOpenExerciseAttempt({ fetch: commandFetch(session) });

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      localStorage.setItem(storageKey, JSON.stringify(answer));
    }, 250);
    return () => {
      window.clearTimeout(timeout);
    };
  }, [answer, storageKey]);

  if (query.isPending)
    return <LoadingRegion label="Chargement de l'exercice" />;
  if (query.data?.status !== 200)
    return <ErrorRegion message="Cet exercice n'est pas disponible." />;
  const exercise = query.data.data;
  const prompt =
    readableBinding(exercise.stimulus_contract) ??
    [
      ...exercise.target_bindings,
      ...exercise.grammar_bindings,
      ...exercise.lexical_bindings,
    ]
      .map(readableBinding)
      .find(Boolean) ??
    "Produisez une réponse dans la langue cible en respectant la consigne de cette étape.";
  const modelAnswer =
    typeof exercise.stimulus_contract.model_answer === "string"
      ? exercise.stimulus_contract.model_answer
      : "Comparez votre production à la consigne.";
  const responseKind: AnswerKind = exercise.response_kinds[0] ?? "text";
  const isAcknowledgement =
    responseKind === "acknowledgement" ||
    responseKind === "self_assessment" ||
    responseKind === "no_answer";
  const persistedAttempt =
    attemptQuery.data?.status === 200 ? attemptQuery.data.data : null;
  const effectiveSubmittedVersion =
    submittedVersion ??
    (persistedAttempt?.submitted_at ? persistedAttempt.version : null);
  const effectiveAnswer: PrimitiveResponse =
    (typeof answer === "string" && answer.length === 0) ||
    (Array.isArray(answer) && answer.length === 0)
      ? ((persistedAttempt?.raw_answer as JsonValueInput | undefined) ?? answer)
      : answer;

  async function submit() {
    setError("");
    let version = attemptVersion ?? persistedAttempt?.version ?? null;
    if ((!opened && persistedAttempt === null) || version === null) {
      const openedResponse = await openAttempt.mutateAsync({
        instanceId,
        data: {
          attempt_id: attemptId,
          attempt_no: 1,
          profile_id:
            activeProfile?.profile_id ?? "00000000-0000-0000-0000-000000000000",
          started_at: new Date().toISOString(),
        },
      });
      const openProblem = responseProblem(openedResponse);
      if (openProblem) {
        setError(openProblem);
        return;
      }
      if (openedResponse.status !== 201) {
        setError("La tentative n'a pas pu être ouverte.");
        return;
      }
      setOpened(true);
      version = openedResponse.data.version;
      setAttemptVersion(version);
    }
    const response = await submitExerciseAttempt(
      attemptId,
      {
        input_locale: targetLanguageTag,
        input_method: "keyboard",
        kind: responseKind,
        raw_value:
          responseKind === "acknowledgement"
            ? true
            : responseKind === "self_assessment"
              ? { confidence: 1 }
              : normalizeResponse(responseKind, answer),
        submitted_at: new Date().toISOString(),
      },
      commandFetch(session, version),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    if (response.status !== 200) {
      setError("La réponse n'a pas pu être enregistrée.");
      return;
    }
    setSubmittedVersion(response.data.version);
    localStorage.removeItem(storageKey);
  }

  async function evaluate() {
    if (effectiveSubmittedVersion === null) return;
    setError("");
    const response = await evaluateExerciseAttempt(
      attemptId,
      {
        evaluated_at: new Date().toISOString(),
      },
      commandFetch(session, effectiveSubmittedVersion),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    if (response.status !== 200) {
      setError("La correction n'a pas pu être enregistrée.");
      return;
    }
    localStorage.removeItem(attemptStorageKey);
    onDone();
  }

  return (
    <section className="exercise-reader">
      <div className="exercise-reader__meta">
        <span>Réponse sauvegardée localement</span>
      </div>
      <div
        className="exercise-prompt"
        dir={activePack?.text_direction}
        lang={targetLanguageTag}
      >
        {prompt}
      </div>
      {exercise.primitive_id.includes("ORAL") ? (
        <TtsAudio
          locale={targetLanguageTag}
          session={session}
          text={modelAnswer}
        />
      ) : null}
      {effectiveSubmittedVersion !== null ? (
        <div className="feedback-panel">
          <div>
            <span>Votre réponse</span>
            <p>
              {isAcknowledgement
                ? "Activité effectuée à voix haute"
                : responseLabel(effectiveAnswer)}
            </p>
          </div>
          <div>
            <span>Réponse modèle</span>
            <p lang={targetLanguageTag}>{modelAnswer}</p>
          </div>
          <p className="feedback-panel__policy">
            Les réponses fermées sont vérifiées automatiquement. Une production
            ouverte est conservée pour le professeur et ne crée aucun crédit de
            maîtrise sans correction légitime.
          </p>
        </div>
      ) : isAcknowledgement ? (
        <div className="self-check">
          <Headphones aria-hidden="true" />
          <div>
            <strong>Faites l'activité à voix haute</strong>
            <p>
              Validez lorsque vous avez terminé. Aucun crédit oral automatique
              n'est attribué.
            </p>
          </div>
        </div>
      ) : (
        <PrimitiveResponseEditor
          contract={{
            ...exercise.response_contract,
            ...exercise.stimulus_contract,
          }}
          kind={responseKind}
          value={answer}
          onChange={setAnswer}
        />
      )}
      {error ? <ErrorRegion message={error} /> : null}
      {effectiveSubmittedVersion === null ? (
        <button
          disabled={
            openAttempt.isPending ||
            attemptQuery.isPending ||
            (!isAcknowledgement && !isResponseComplete(responseKind, answer))
          }
          type="button"
          onClick={() => void submit()}
        >
          Valider la réponse <ArrowRight aria-hidden="true" size={18} />
        </button>
      ) : (
        <button
          type="button"
          onClick={() => void evaluate()}
        >
          Corriger et continuer <ArrowRight aria-hidden="true" size={18} />
        </button>
      )}
    </section>
  );
}

export function SprintPage() {
  const { runId = "" } = useParams();
  const session = useSession();
  const { activePack } = useActiveProfile();
  const navigate = useNavigate();
  const query = useGetSprintRun(runId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const [exerciseOffset, setExerciseOffset] = useState(0);
  const [selectedBlockOffset, setSelectedBlockOffset] = useState<number | null>(
    null,
  );
  const [error, setError] = useState("");

  const run = query.data?.status === 200 ? query.data.data : null;
  const blocks = useMemo<SprintBlockResponse[]>(
    () => (run ? [...run.blocks].sort((a, b) => a.ordinal - b.ordinal) : []),
    [run],
  );
  const blockOffset =
    selectedBlockOffset ??
    resumeBlockOffset(blocks, run?.current_block_id ?? null);
  const block: SprintBlockResponse | undefined = blocks[blockOffset];
  const instanceId = block?.exercise_instance_ids[exerciseOffset];
  const targetLanguageTag = activePack?.target_language_tag ?? "und";

  if (query.isPending)
    return (
      <div className="sprint-shell">
        <LoadingRegion label="Reprise de la séance" />
      </div>
    );
  if (!run || !block)
    return (
      <div className="sprint-shell">
        <ErrorRegion message="Cette séance n'existe pas ou n'est plus accessible." />
        <Link to="/today">Retour à aujourd'hui</Link>
      </div>
    );
  const currentRun = run;
  const currentBlock = block;

  async function refreshRun() {
    const refreshed = await query.refetch();
    if (refreshed.data?.status !== 200) {
      setError("La séance n'a pas pu être synchronisée.");
      return null;
    }
    return refreshed.data;
  }

  async function next() {
    if (exerciseOffset + 1 < currentBlock.exercise_instance_ids.length) {
      setExerciseOffset((value) => value + 1);
      return;
    }
    if (blockOffset + 1 < blocks.length) {
      setSelectedBlockOffset(blockOffset + 1);
      setExerciseOffset(0);
      return;
    }
    const latestRun = await refreshRun();
    if (!latestRun) return;
    const response = await completeSprintRun(
      runId,
      {},
      commandFetch(session, latestRun.data.version),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    if (currentRun.plan_kind === "daily") {
      localStorage.setItem(
        `polyglot.completed-day.${currentRun.profile_id}`,
        new Date().toISOString().slice(0, 10),
      );
    }
    localStorage.removeItem(
      currentRun.plan_kind === "free"
        ? freePracticeRunStorageKey(session.account_id, currentRun.profile_id)
        : activeRunStorageKey(session.account_id, currentRun.profile_id),
    );
    void navigate(currentRun.plan_kind === "free" ? "/practice" : "/progress");
  }

  async function pause() {
    const latestRun = await refreshRun();
    if (!latestRun) return;
    const response = await interruptSprintRun(
      runId,
      { reason: "learner_pause" },
      commandFetch(session, latestRun.data.version),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    void navigate(currentRun.plan_kind === "free" ? "/practice" : "/today");
  }

  const completed =
    blocks
      .slice(0, blockOffset)
      .reduce(
        (sum: number, item: SprintBlockResponse) =>
          sum + item.exercise_instance_ids.length,
        0,
      ) + exerciseOffset;
  const total = blocks.reduce(
    (sum: number, item: SprintBlockResponse) =>
      sum + item.exercise_instance_ids.length,
    0,
  );

  return (
    <div className="sprint-shell">
      <header className="sprint-header">
        <Link
          aria-label="Quitter la séance"
          to={currentRun.plan_kind === "free" ? "/practice" : "/today"}
        >
          <ArrowLeft aria-hidden="true" />
        </Link>
        <div>
          <span>
            Étape {blockOffset + 1} sur {blocks.length}
          </span>
          <strong>
            {sprintFamilyLabel(currentBlock.family, targetLanguageTag)}
          </strong>
        </div>
        <button
          aria-label="Mettre la séance en pause"
          className="icon-button secondary-button"
          type="button"
          onClick={() => void pause()}
        >
          <Pause aria-hidden="true" />
        </button>
      </header>
      <div
        aria-label={`${String(completed)} exercices terminés sur ${String(total)}`}
        className="sprint-progress"
        role="progressbar"
        aria-valuemax={total}
        aria-valuemin={0}
        aria-valuenow={completed}
      >
        <span
          style={{ width: `${String(total ? (completed / total) * 100 : 0)}%` }}
        />
      </div>
      <main className="sprint-stage">
        <p className="eyebrow">
          {currentBlock.required ? "Étape essentielle" : "Approfondissement"}
        </p>
        <h1>{sprintFamilyLabel(currentBlock.family, targetLanguageTag)}</h1>
        {instanceId ? (
          <ExerciseReader
            key={instanceId}
            instanceId={instanceId}
            onDone={() => void next()}
          />
        ) : currentBlock.family === "reflection_close" ? (
          <section className="exercise-reader reflection-close">
            <div className="exercise-prompt">
              Repérez mentalement un mot devenu plus accessible et une structure
              à reprendre demain.
            </div>
            <p>
              Les réponses, rappels et auto-évaluations de cette séance sont
              déjà enregistrés dans votre progression.
            </p>
            <button type="button" onClick={() => void next()}>
              Terminer la séance <ArrowRight aria-hidden="true" size={18} />
            </button>
          </section>
        ) : (
          <ErrorRegion message="Cette étape ne contient aucun exercice exploitable." />
        )}
        {error ? <ErrorRegion message={error} /> : null}
      </main>
    </div>
  );
}
