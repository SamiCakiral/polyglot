import { ArrowLeft, ArrowRight, Headphones, Pause } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useSession } from "../../app/session-context";
import { useActiveProfile } from "../../app/profile-state";
import {
  ErrorRegion,
  LoadingRegion,
  StatusPill,
} from "../../components/product-ui";
import { TtsAudio } from "../../components/tts-audio";
import type { AnswerKind, SprintBlockResponse } from "../../generated/model";
import {
  selfAssessExerciseAttempt,
  submitExerciseAttempt,
  useCompleteSprintRun,
  useGetExerciseInstance,
  useGetSprintRun,
  useInterruptSprintRun,
  useOpenExerciseAttempt,
} from "../../generated/polyglot";
import { commandFetch, queryFetch, responseProblem } from "../../lib/api";
import { uuid7 } from "../../lib/ids";

const familyLabels: Record<string, string> = {
  vocabulary: "Vocabulaire du jour",
  memory_review: "Rappels à échéance",
  version: "Comprendre l'italien",
  grammar_toolbox: "Boîte grammaticale",
  gym: "Gym de transformation",
  shadowing: "Écoute et shadowing",
  free_writing: "Expression écrite",
  delayed_recode: "Inversion J+1",
};

const meaningChoices: readonly (readonly [number, string])[] = [
  [0, "Non"],
  [0.5, "En partie"],
  [1, "Oui"],
];
const formChoices: readonly (readonly [number, string])[] = [
  [0, "Non"],
  [0.5, "Presque"],
  [1, "Oui"],
];

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

function ExerciseReader({
  instanceId,
  onDone,
}: {
  instanceId: string;
  onDone: () => void;
}) {
  const session = useSession();
  const { activeProfile } = useActiveProfile();
  const query = useGetExerciseInstance(instanceId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const [attemptId] = useState(uuid7);
  const [attemptVersion, setAttemptVersion] = useState<number | null>(null);
  const storageKey = `polyglot.draft.${instanceId}`;
  const [answer, setAnswer] = useState(
    () => localStorage.getItem(storageKey) ?? "",
  );
  const [opened, setOpened] = useState(false);
  const [submittedVersion, setSubmittedVersion] = useState<number | null>(null);
  const [meaningScore, setMeaningScore] = useState<number | null>(null);
  const [formScore, setFormScore] = useState<number | null>(null);
  const [error, setError] = useState("");
  const openAttempt = useOpenExerciseAttempt({ fetch: commandFetch(session) });

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      localStorage.setItem(storageKey, answer);
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
    "Produisez une réponse en italien en respectant la consigne de cette étape.";
  const modelAnswer =
    typeof exercise.stimulus_contract.model_answer === "string"
      ? exercise.stimulus_contract.model_answer
      : "Comparez votre production à la consigne.";
  const responseKind: AnswerKind = exercise.response_kinds[0] ?? "text";
  const isAcknowledgement =
    responseKind === "acknowledgement" || responseKind === "self_assessment";

  async function submit() {
    setError("");
    let version = attemptVersion;
    if (!opened || version === null) {
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
        input_locale: "it-IT",
        input_method: "keyboard",
        kind: responseKind,
        raw_value: isAcknowledgement ? { acknowledged: true } : answer,
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

  async function selfAssess() {
    if (
      submittedVersion === null ||
      meaningScore === null ||
      formScore === null
    )
      return;
    setError("");
    const response = await selfAssessExerciseAttempt(
      attemptId,
      {
        meaning: meaningScore,
        form: formScore,
        reviewed_at: new Date().toISOString(),
      },
      commandFetch(session, submittedVersion),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    if (response.status !== 200) {
      setError("L'auto-évaluation n'a pas pu être enregistrée.");
      return;
    }
    onDone();
  }

  return (
    <section className="exercise-reader">
      <div className="exercise-reader__meta">
        <StatusPill>{exercise.primitive_id.replaceAll("_", " ")}</StatusPill>
        <span>Réponse sauvegardée localement</span>
      </div>
      <div className="exercise-prompt" lang="it">
        {prompt}
      </div>
      {exercise.primitive_id.includes("ORAL") ? (
        <TtsAudio session={session} text={modelAnswer} />
      ) : null}
      {submittedVersion !== null ? (
        <div className="feedback-panel">
          <div>
            <span>Votre réponse</span>
            <p>
              {isAcknowledgement ? "Activité effectuée à voix haute" : answer}
            </p>
          </div>
          <div>
            <span>Réponse modèle</span>
            <p lang="it">{modelAnswer}</p>
          </div>
          <fieldset>
            <legend>Le sens est-il juste ?</legend>
            <div className="score-options">
              {meaningChoices.map(([score, label]) => (
                <label key={label}>
                  <input
                    checked={meaningScore === score}
                    name={`${attemptId}-meaning`}
                    type="radio"
                    onChange={() => {
                      setMeaningScore(score);
                    }}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>La forme est-elle naturelle ?</legend>
            <div className="score-options">
              {formChoices.map(([score, label]) => (
                <label key={label}>
                  <input
                    checked={formScore === score}
                    name={`${attemptId}-form`}
                    type="radio"
                    onChange={() => {
                      setFormScore(score);
                    }}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>
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
        <label className="answer-field">
          Votre réponse
          <textarea
            autoFocus
            rows={6}
            value={answer}
            onChange={(event) => {
              setAnswer(event.target.value);
            }}
          />
        </label>
      )}
      {error ? <ErrorRegion message={error} /> : null}
      {submittedVersion === null ? (
        <button
          disabled={
            openAttempt.isPending ||
            (!isAcknowledgement && answer.trim().length === 0)
          }
          type="button"
          onClick={() => void submit()}
        >
          Valider la réponse <ArrowRight aria-hidden="true" size={18} />
        </button>
      ) : (
        <button
          disabled={meaningScore === null || formScore === null}
          type="button"
          onClick={() => void selfAssess()}
        >
          Enregistrer et continuer <ArrowRight aria-hidden="true" size={18} />
        </button>
      )}
    </section>
  );
}

export function SprintPage() {
  const { runId = "" } = useParams();
  const session = useSession();
  const navigate = useNavigate();
  const query = useGetSprintRun(runId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const runVersion =
    query.data?.status === 200 ? query.data.data.version : undefined;
  const interrupt = useInterruptSprintRun({
    fetch: commandFetch(session, runVersion),
  });
  const complete = useCompleteSprintRun({
    fetch: commandFetch(session, runVersion),
  });
  const [exerciseOffset, setExerciseOffset] = useState(0);
  const [blockOffset, setBlockOffset] = useState(0);
  const [error, setError] = useState("");

  const run = query.data?.status === 200 ? query.data.data : null;
  const blocks = useMemo<SprintBlockResponse[]>(
    () => (run ? [...run.blocks].sort((a, b) => a.ordinal - b.ordinal) : []),
    [run],
  );
  const block: SprintBlockResponse | undefined = blocks[blockOffset];
  const instanceId = block?.exercise_instance_ids[exerciseOffset];

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
  const currentBlock = block;

  async function next() {
    if (exerciseOffset + 1 < currentBlock.exercise_instance_ids.length) {
      setExerciseOffset((value) => value + 1);
      return;
    }
    if (blockOffset + 1 < blocks.length) {
      setBlockOffset((value) => value + 1);
      setExerciseOffset(0);
      return;
    }
    const response = await complete.mutateAsync({
      runId,
      data: { reason: "completed_by_learner" },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    localStorage.removeItem("polyglot.active-run");
    void navigate("/progress");
  }

  async function pause() {
    const response = await interrupt.mutateAsync({
      runId,
      data: { reason: "learner_pause" },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    void navigate("/today");
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
        <Link aria-label="Quitter la séance" to="/today">
          <ArrowLeft aria-hidden="true" />
        </Link>
        <div>
          <span>
            Étape {blockOffset + 1} sur {blocks.length}
          </span>
          <strong>
            {familyLabels[currentBlock.family] ?? currentBlock.family}
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
        <h1>{familyLabels[currentBlock.family] ?? "Exercice"}</h1>
        {instanceId ? (
          <ExerciseReader
            key={instanceId}
            instanceId={instanceId}
            onDone={() => void next()}
          />
        ) : null}
        {error ? <ErrorRegion message={error} /> : null}
      </main>
    </div>
  );
}
