import {
  ArrowRight,
  Ear,
  Eye,
  Mic2,
  PenLine,
  Square,
  Timer,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
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
import { TtsAudio } from "../../components/tts-audio";
import type {
  AssessmentItemResponse,
  CurrentSessionResponse,
} from "../../generated/model";
import {
  getTtsCapabilities,
  saveAssessmentResponse,
  startAssessment,
  submitAssessment,
  useGetAssessmentRun,
  usePrepareAssessment,
} from "../../generated/polyglot";
import { commandFetch, queryFetch, responseProblem } from "../../lib/api";
import { uuid7 } from "../../lib/ids";

const modalities = [
  {
    id: "reading",
    label: "Compréhension écrite",
    icon: Eye,
    note: "Lire puis répondre sans aide extérieure.",
  },
  {
    id: "listening",
    label: "Compréhension orale",
    icon: Ear,
    note: "Écoutes limitées et réponses contextualisées.",
  },
  {
    id: "writing",
    label: "Expression écrite",
    icon: PenLine,
    note: "Produire un texte nouveau sous contrainte.",
  },
  {
    id: "speaking",
    label: "Expression orale",
    icon: Mic2,
    note: "Protocole guidé, sans crédit automatique au MVP.",
  },
] as const;

const speakingScores = [
  ["difficult", "Difficile"],
  ["partial", "Partielle"],
  ["comfortable", "À l'aise"],
] as const;

function promptText(item: AssessmentItemResponse, key: string): string | null {
  const value = item.prompt[key];
  return typeof value === "string" ? value : null;
}

function promptOptions(item: AssessmentItemResponse): string[] {
  const value = item.prompt.options;
  return Array.isArray(value)
    ? value.filter((option): option is string => typeof option === "string")
    : [];
}

export function AssessPage() {
  return (
    <div className="page-flow">
      <PageHeader
        eyebrow="Mesure indépendante"
        title="Évaluer mon niveau"
        description="Chaque test mesure une compétence séparément à partir de contenu nouveau."
      />
      <div className="assessment-grid">
        {modalities.map(({ id, label, icon: Icon, note }) => (
          <article key={id}>
            <Icon aria-hidden="true" />
            <div>
              <h2>{label}</h2>
              <p>{note}</p>
            </div>
            <StatusPill tone={id === "speaking" ? "warn" : "neutral"}>
              {id === "speaking" ? "Protocole seul" : "Disponible"}
            </StatusPill>
            <Link className="text-link" to={`/assess/${id}`}>
              Voir le protocole <ArrowRight aria-hidden="true" size={17} />
            </Link>
          </article>
        ))}
      </div>
      <section className="integrity-note">
        <strong>Une évaluation n'est pas un entraînement</strong>
        <p>
          Elle ne réutilise pas les réponses de vos séances et ne transforme
          jamais une absence de fournisseur en réussite ou en échec.
        </p>
      </section>
    </div>
  );
}

export function AssessmentProtocolPage() {
  const { modality = "reading" } = useParams();
  const { activeProfile } = useActiveProfile();
  const session = useSession();
  const navigate = useNavigate();
  const prepare = usePrepareAssessment({ fetch: commandFetch(session) });
  const [error, setError] = useState("");
  const meta = modalities.find((item) => item.id === modality) ?? modalities[0];
  if (!activeProfile) return <NoProfile />;
  const profileId = activeProfile.profile_id;

  async function begin() {
    setError("");
    const capabilities: string[] = [];
    if (meta.id === "listening") {
      const response = await getTtsCapabilities(
        { language: "it-IT" },
        queryFetch(),
      );
      const problem = responseProblem(response);
      if (problem) {
        setError(problem);
        return;
      }
      if (
        response.status !== 200 ||
        !response.data.voices.some(
          (voice) =>
            voice.voice_id === "Alice" && voice.availability === "available",
        )
      ) {
        setError(
          "La voix italienne Alice est indisponible. Le test d'écoute ne peut pas démarrer.",
        );
        return;
      }
      capabilities.push("tts");
    }
    const runId = uuid7();
    const prepared = await prepare.mutateAsync({
      profileId,
      data: { capabilities, modality: meta.id, run_id: runId, seed: uuid7() },
    });
    const problem = responseProblem(prepared);
    if (problem) {
      setError(problem);
      return;
    }
    if (prepared.status !== 201) {
      setError("L'évaluation n'a pas pu être préparée.");
      return;
    }
    const started = await startAssessment(
      runId,
      {},
      commandFetch(session, prepared.data.version),
    );
    const startProblem = responseProblem(started);
    if (startProblem) {
      setError(startProblem);
      return;
    }
    void navigate(`/assess/runs/${runId}`);
  }

  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow="Protocole"
        title={meta.label}
        description={meta.note}
      />
      <section className="protocol-sheet">
        <Timer aria-hidden="true" />
        <h2>Avant de commencer</h2>
        <ol>
          <li>Installez-vous sans traducteur ni notes.</li>
          <li>Le chronomètre démarre avec la première consigne.</li>
          <li>
            Vous pourrez interrompre uniquement si le protocole l'autorise.
          </li>
        </ol>
        {meta.id === "speaking" ? (
          <p className="form-warning">
            Votre enregistrement peut être conservé localement, mais restera non
            évaluable sans revue humaine.
          </p>
        ) : null}
        {error ? <ErrorRegion message={error} /> : null}
        <button
          disabled={prepare.isPending}
          type="button"
          onClick={() => void begin()}
        >
          Commencer l'évaluation <ArrowRight aria-hidden="true" size={18} />
        </button>
      </section>
    </div>
  );
}

function AssessmentTimer({
  deadlineAt,
  serverNow,
  timeLimitMs,
}: {
  deadlineAt: string | null;
  serverNow: string;
  timeLimitMs: number;
}) {
  const [remaining, setRemaining] = useState(() =>
    deadlineAt
      ? Math.max(
          0,
          new Date(deadlineAt).getTime() - new Date(serverNow).getTime(),
        )
      : timeLimitMs,
  );
  useEffect(() => {
    const interval = window.setInterval(() => {
      setRemaining((value) => Math.max(0, value - 1000));
    }, 1000);
    return () => {
      window.clearInterval(interval);
    };
  }, []);
  const minutes = Math.floor(remaining / 60000);
  const seconds = Math.floor((remaining % 60000) / 1000);
  return (
    <strong
      aria-label={`${String(minutes)} minutes et ${String(seconds)} secondes restantes`}
    >
      {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
    </strong>
  );
}

function SpeakingRecorder({ onRecorded }: { onRecorded: () => void }) {
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const [recording, setRecording] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function start() {
    setError("");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      chunks.current = [];
      const next = new MediaRecorder(stream.current);
      next.addEventListener("dataavailable", (event) => {
        if (event.data.size) chunks.current.push(event.data);
      });
      next.addEventListener("stop", () => {
        setAudioUrl(
          URL.createObjectURL(
            new Blob(chunks.current, { type: next.mimeType }),
          ),
        );
        stream.current?.getTracks().forEach((track) => {
          track.stop();
        });
        onRecorded();
      });
      recorder.current = next;
      next.start();
      setRecording(true);
    } catch {
      setError(
        "Le microphone n'est pas disponible. Vous pouvez effectuer la consigne sans enregistrer.",
      );
    }
  }

  function stop() {
    recorder.current?.stop();
    setRecording(false);
  }

  return (
    <div className="speaking-recorder">
      {recording ? (
        <button className="danger-button" type="button" onClick={stop}>
          <Square aria-hidden="true" size={17} /> Arrêter
        </button>
      ) : (
        <button
          className="secondary-button"
          type="button"
          onClick={() => void start()}
        >
          <Mic2 aria-hidden="true" size={17} /> Enregistrer localement
        </button>
      )}
      {audioUrl ? <audio controls src={audioUrl} /> : null}
      {error ? (
        <p className="form-warning" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function AssessmentItemControl({
  item,
  modality,
  runId,
  session,
  value,
  onChange,
}: {
  item: AssessmentItemResponse;
  modality: string;
  runId: string;
  session: CurrentSessionResponse;
  value: string;
  onChange: (value: string) => void;
}) {
  const title = promptText(item, "title");
  const body = promptText(item, "body");
  const question =
    promptText(item, "question") ?? title ?? "Répondez à la consigne";
  const options = promptOptions(item);
  return (
    <article className="assessment-item">
      {title ? <h2>{title}</h2> : null}
      {body ? <p lang="it">{body}</p> : null}
      {modality === "listening" ? (
        <TtsAudio
          assessmentItemId={item.item_id}
          assessmentRunId={runId}
          label="Écouter le segment"
          maxPlays={item.max_plays}
          session={session}
        />
      ) : null}
      {options.length ? (
        <fieldset>
          <legend>{question}</legend>
          <div className="choice-stack">
            {options.map((option) => (
              <label className="choice-row" key={option}>
                <input
                  checked={value === option}
                  name={item.item_id}
                  type="radio"
                  value={option}
                  onChange={() => {
                    onChange(option);
                  }}
                />
                <span>{option}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : modality === "speaking" ? (
        <div className="oral-assessment">
          <p>{question}</p>
          <SpeakingRecorder
            onRecorded={() => {
              onChange("recorded_self_assessment");
            }}
          />
          <fieldset>
            <legend>
              Après la réalisation, comment évaluez-vous votre aisance ?
            </legend>
            <div className="score-options">
              {speakingScores.map(([score, label]) => (
                <label key={score}>
                  <input
                    checked={value === score}
                    name={item.item_id}
                    type="radio"
                    onChange={() => {
                      onChange(score);
                    }}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      ) : (
        <label className="answer-field">
          {question}
          <textarea
            rows={6}
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
            }}
          />
        </label>
      )}
    </article>
  );
}

export function AssessmentRunPage() {
  const { assessmentRunId = "" } = useParams();
  const session = useSession();
  const navigate = useNavigate();
  const query = useGetAssessmentRun(assessmentRunId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (query.isPending)
    return <LoadingRegion label="Ouverture de l'évaluation" />;
  if (query.data?.status !== 200)
    return <ErrorRegion message="Cette évaluation n'est pas disponible." />;
  const run = query.data.data;
  const items = run.sections.flatMap((section) => section.items);
  const allAnswered = items.every(
    (item) => (answers[item.item_id] ?? "").trim().length > 0,
  );

  async function finish() {
    setBusy(true);
    setError("");
    let version = run.version;
    for (const item of items) {
      const response = await saveAssessmentResponse(
        run.run_id,
        item.item_id,
        {
          answer: { value: answers[item.item_id] ?? "" },
          expected_response_version: item.response_version,
        },
        commandFetch(session, version),
      );
      const problem = responseProblem(response);
      if (problem) {
        setError(problem);
        setBusy(false);
        return;
      }
      if (response.status !== 200) {
        setError("La réponse n'a pas pu être enregistrée.");
        setBusy(false);
        return;
      }
      version = response.data.version;
    }
    const response = await submitAssessment(
      run.run_id,
      {},
      commandFetch(session, version),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      setBusy(false);
      return;
    }
    void navigate("/progress");
  }

  return (
    <div className="assessment-run">
      <header>
        <span>
          {modalities.find((item) => item.id === run.modality)?.label ??
            run.modality}
        </span>
        <AssessmentTimer
          deadlineAt={run.deadline_at}
          serverNow={run.server_now}
          timeLimitMs={run.time_limit_ms}
        />
      </header>
      <main>
        <h1>Évaluation en cours</h1>
        {run.sections.map((section) => (
          <section className="assessment-section" key={section.section_id}>
            <p className="eyebrow">{section.title}</p>
            <p>{section.instructions}</p>
            {section.items.map((item) => (
              <AssessmentItemControl
                item={item}
                key={item.item_id}
                modality={run.modality}
                runId={run.run_id}
                session={session}
                value={answers[item.item_id] ?? ""}
                onChange={(value) => {
                  setAnswers((current) => ({
                    ...current,
                    [item.item_id]: value,
                  }));
                }}
              />
            ))}
          </section>
        ))}
        {error ? <ErrorRegion message={error} /> : null}
        <button
          disabled={!allAnswered || busy}
          type="button"
          onClick={() => void finish()}
        >
          {busy ? "Enregistrement..." : "Remettre l'évaluation"}
        </button>
      </main>
    </div>
  );
}
