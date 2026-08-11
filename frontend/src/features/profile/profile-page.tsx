import { ArrowRight, Check, Languages, Milestone } from "lucide-react";
import { type SyntheticEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useSession } from "../../app/session-context";
import { useActiveProfile } from "../../app/profile-state";
import {
  ErrorRegion,
  LoadingRegion,
  PageHeader,
  StatusPill,
} from "../../components/product-ui";
import type { PlacementItemResponse } from "../../generated/model";
import {
  completeDiagnostic,
  completeFoundationGate,
  enrollInModule,
  getDiagnosticSummary,
  startDiagnostic,
  startFoundationRun,
  submitDiagnosticResponse,
  useCreateLanguageProfile,
  useGetPlacementManifest,
  useGetFoundationManifest,
  useGetFoundationRun,
  useListLanguagePacks,
  useListLearningModules,
  useUpdateLearningGoals,
} from "../../generated/polyglot";
import {
  commandFetch,
  queryFetch,
  responseProblem,
  todayIso,
} from "../../lib/api";
import { uuid7 } from "../../lib/ids";

const goalOptions = [
  "Voyager avec autonomie",
  "Tenir une conversation",
  "Lire et comprendre",
  "Écrire avec précision",
] as const;

export function LanguageProfilePage() {
  const session = useSession();
  const navigate = useNavigate();
  const { activeProfile, isPending, refresh } = useActiveProfile();
  const [selectedPackRevisionId, setSelectedPackRevisionId] = useState("");
  const packsQuery = useListLanguagePacks(
    { limit: 20 },
    { fetch: queryFetch(), query: { retry: false } },
  );
  const modulesQuery = useListLearningModules({
    fetch: queryFetch(),
    query: { retry: false },
  });
  const packs = packsQuery.data?.status === 200 ? packsQuery.data.data.items : [];
  const pack = activeProfile
    ? packs.find((item) => item.target_variety_id === activeProfile.target_variety_id)
    : packs.find((item) => item.pack_revision_id === selectedPackRevisionId) ?? packs[0];
  const displayNames = new Intl.DisplayNames(["fr"], { type: "language" });
  const targetName = pack
    ? (displayNames.of(pack.target_language_tag) ?? pack.target_language_tag)
    : "la langue cible";
  const supportName = pack?.support_language_tags[0]
    ? (displayNames.of(pack.support_language_tags[0]) ?? pack.support_language_tags[0])
    : "la langue d'appui";
  const manifestQuery = useGetPlacementManifest(pack?.pack_revision_id ?? "", {
    fetch: queryFetch(),
    query: { enabled: Boolean(pack), retry: false },
  });
  const createProfile = useCreateLanguageProfile({
    fetch: commandFetch(session),
  });
  const updateGoals = useUpdateLearningGoals({
    fetch: commandFetch(session, activeProfile?.version),
  });
  const [goals, setGoals] = useState<string[]>([
    goalOptions[0],
    goalOptions[1],
  ]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [foundationRunId, setFoundationRunId] = useState(
    () => localStorage.getItem("polyglot.foundation-run") ?? "",
  );
  const [error, setError] = useState("");

  const manifest =
    manifestQuery.data?.status === 200 ? manifestQuery.data.data : null;
  const modules =
    modulesQuery.data?.status === 200 ? modulesQuery.data.data : [];
  const allAnswered = useMemo(
    () =>
      Boolean(
        manifest?.items.every((item) =>
          (answers[item.item_revision_id] ?? "").trim(),
        ),
      ),
    [answers, manifest],
  );

  if (isPending || packsQuery.isPending) {
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader eyebrow="Profil de langue" title="Votre parcours" />
        <LoadingRegion label="Chargement des parcours" />
      </div>
    );
  }

  async function create(event: SyntheticEvent<HTMLFormElement, SubmitEvent>) {
    event.preventDefault();
    if (!pack?.support_variety_ids[0]) return;
    setError("");
    const response = await createProfile.mutateAsync({
      data: {
        native_variety_id: pack.support_variety_ids[0],
        target_variety_id: pack.target_variety_id,
      },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    await refresh();
  }

  async function saveGoals() {
    if (!activeProfile) return;
    setError("");
    const response = await updateGoals.mutateAsync({
      profileId: activeProfile.profile_id,
      data: { goals },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    await refresh();
  }

  async function enroll(profileId: string) {
    const module = modules[0];
    if (!module)
      throw new Error(`Aucun module ${targetName.toLocaleLowerCase("fr")} publié n'est disponible.`);
    const enrollmentId = uuid7();
    const response = await enrollInModule(
      profileId,
      {
        enrollment_id: enrollmentId,
        module_revision_id: module.module_revision_id,
        pedagogical_day: todayIso(),
      },
      commandFetch(session),
    );
    const problem = responseProblem(response);
    if (problem) throw new Error(problem);
    localStorage.setItem("polyglot.active-enrollment", enrollmentId);
  }

  async function finishDiagnostic() {
    if (!activeProfile || !pack || !manifest) return;
    setBusy(true);
    setError("");
    try {
      const storageKey = `polyglot.diagnostic-run.${activeProfile.profile_id}`;
      const storedRunId = localStorage.getItem(storageKey);
      let runId = storedRunId ?? "";
      let version = 1;
      if (storedRunId) {
        const existing = await getDiagnosticSummary(storedRunId, queryFetch());
        if (existing.status === 200 && existing.data.status === "in_progress") {
          version = existing.data.version;
        } else {
          localStorage.removeItem(storageKey);
          runId = "";
        }
      }
      if (!runId) {
        const started = await startDiagnostic(
          activeProfile.profile_id,
          {
            pack_revision_id: pack.pack_revision_id,
            policy_revision_id: uuid7(),
            seed: uuid7(),
          },
          commandFetch(session, activeProfile.version),
        );
        const startProblem = responseProblem(started);
        if (startProblem) throw new Error(startProblem);
        if (started.status !== 201)
          throw new Error("Le diagnostic n'a pas pu démarrer.");
        runId = started.data.diagnostic_run_id;
        version = started.data.version;
        localStorage.setItem(storageKey, runId);
      }
      for (const item of manifest.items) {
        if (item.ordinal < version) continue;
        const response = await submitDiagnosticResponse(
          runId,
          {
            answer: { value: answers[item.item_revision_id] ?? "" },
            item_revision_id: item.item_revision_id,
            ordinal: item.ordinal,
          },
          commandFetch(session, version),
        );
        const problem = responseProblem(response);
        if (problem) throw new Error(problem);
        if (response.status !== 200)
          throw new Error("Une réponse du diagnostic n'a pas été enregistrée.");
        version = response.data.version;
      }
      const completed = await completeDiagnostic(
        runId,
        commandFetch(session, version),
      );
      const completionProblem = responseProblem(completed);
      if (completionProblem) throw new Error(completionProblem);
      if (completed.status !== 200)
        throw new Error("Le placement n'a pas pu être calculé.");
      localStorage.removeItem(storageKey);
      await refresh();
      if (completed.data.classification === "intermediate") {
        await enroll(activeProfile.profile_id);
        void navigate("/today");
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Le diagnostic a été interrompu.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function beginFoundations() {
    if (!activeProfile || !pack?.foundation_revision_id) return;
    setBusy(true);
    setError("");
    try {
      const response = await startFoundationRun(
        activeProfile.profile_id,
        {
          foundation_revision_id: pack.foundation_revision_id,
          pack_revision_id: pack.pack_revision_id,
          seed: uuid7(),
        },
        commandFetch(session, activeProfile.version),
      );
      const problem = responseProblem(response);
      if (problem) throw new Error(problem);
      if (response.status !== 201)
        throw new Error("Les fondations n'ont pas pu être préparées.");
      localStorage.setItem(
        "polyglot.foundation-run",
        response.data.foundation_run_id,
      );
      setFoundationRunId(response.data.foundation_run_id);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Les fondations ne sont pas disponibles.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!pack) {
    return (
      <ErrorRegion message="Aucun parcours linguistique n'est publié sur cette installation." />
    );
  }

  if (!activeProfile) {
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow="Étape 1 sur 3"
          title="Votre profil de langue"
          description="Choisissez la langue à apprendre et la langue utilisée pour les explications."
        />
        <form
          className="onboarding-panel"
          onSubmit={(event) => void create(event)}
        >
          <label className="answer-field">
            Parcours
            <select
              value={pack.pack_revision_id}
              onChange={(event) => {
                setSelectedPackRevisionId(event.target.value);
              }}
            >
              {packs.map((item) => (
                <option key={item.pack_revision_id} value={item.pack_revision_id}>
                  {(displayNames.of(item.support_language_tags[0] ?? "") ?? item.support_language_tags[0])}
                  {" → "}
                  {(displayNames.of(item.target_language_tag) ?? item.target_language_tag)}
                </option>
              ))}
            </select>
          </label>
          <div className="language-pair" aria-label={`${supportName} vers ${targetName}`}>
            <div>
              <span>Langue d'appui</span>
              <strong>{supportName}</strong>
              <small>{pack.support_language_tags[0]}</small>
            </div>
            <Languages aria-hidden="true" />
            <div>
              <span>Langue cible</span>
              <strong>{targetName}</strong>
              <small>{pack.target_language_tag}</small>
            </div>
          </div>
          <p>
            Les explications utilisent {supportName.toLocaleLowerCase("fr")} et les activités
            travaillent {targetName.toLocaleLowerCase("fr")}.
          </p>
          {error ? <ErrorRegion message={error} /> : null}
          <button disabled={createProfile.isPending} type="submit">
            {createProfile.isPending ? "Création..." : "Créer ce profil"}
          </button>
        </form>
      </div>
    );
  }

  if (activeProfile.goals.length === 0) {
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow="Étape 2 sur 3"
          title={`${supportName} → ${targetName}`}
          description="Vos choix orientent les situations proposées, sans masquer les lacunes à retravailler."
          action={<StatusPill tone="warn">objectifs</StatusPill>}
        />
        <section className="onboarding-panel">
          <div className="step-marker">
            <Check aria-hidden="true" size={18} /> Langues configurées
          </div>
          <h2>Ce que vous voulez savoir faire</h2>
          <div className="choice-grid">
            {goalOptions.map((goal) => (
              <label className="choice-row" key={goal}>
                <input
                  checked={goals.includes(goal)}
                  type="checkbox"
                  onChange={() => {
                    setGoals((current) =>
                      current.includes(goal)
                        ? current.filter((item) => item !== goal)
                        : [...current, goal],
                    );
                  }}
                />
                <span>{goal}</span>
              </label>
            ))}
          </div>
          {error ? <ErrorRegion message={error} /> : null}
          <button
            disabled={updateGoals.isPending || goals.length === 0}
            type="button"
            onClick={() => void saveGoals()}
          >
            Enregistrer et continuer
          </button>
        </section>
      </div>
    );
  }

  if (activeProfile.status === "foundations") {
    if (foundationRunId) {
      return (
        <FoundationFlow
          packRevisionId={pack.pack_revision_id}
          runId={foundationRunId}
          onComplete={refresh}
          onMissing={() => {
            localStorage.removeItem("polyglot.foundation-run");
            setFoundationRunId("");
          }}
        />
      );
    }
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow="Fondations requises"
          title="Construire des bases fiables"
          description="Le placement conseille un court sas sur les sons, la lecture et les échanges de survie."
        />
        <section className="onboarding-panel">
          <Milestone aria-hidden="true" size={28} />
          <h2>Deux contrôles espacés</h2>
          <p>
            Le premier passage enseigne et mesure les bases. Un second contrôle
            à J+1 vérifie qu'elles restent disponibles.
          </p>
          {error ? <ErrorRegion message={error} /> : null}
          <button
            disabled={busy}
            type="button"
            onClick={() => void beginFoundations()}
          >
            Commencer les fondations <ArrowRight aria-hidden="true" size={18} />
          </button>
        </section>
      </div>
    );
  }

  if (activeProfile.status === "active") {
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow="Profil prêt"
          title={`Votre parcours ${targetName.toLocaleLowerCase("fr")}`}
          description="Le placement est terminé. Le premier module peut maintenant commencer."
        />
        <section className="onboarding-panel">
          <Check aria-hidden="true" size={28} />
          <h2>Entrer en contact et réparer un échange</h2>
          <p>
            Trois journées relient vocabulaire, compréhension, boîte
            grammaticale, Gym, oral et production.
          </p>
          {error ? <ErrorRegion message={error} /> : null}
          <button
            disabled={busy || modules.length === 0}
            type="button"
            onClick={() => {
              setBusy(true);
              void enroll(activeProfile.profile_id)
                .then(() => {
                  void navigate("/today");
                })
                .catch((caught: unknown) => {
                  setError(
                    caught instanceof Error
                      ? caught.message
                      : "L'inscription a échoué.",
                  );
                })
                .finally(() => {
                  setBusy(false);
                });
            }}
          >
            Commencer le module <ArrowRight aria-hidden="true" size={18} />
          </button>
        </section>
      </div>
    );
  }

  if (manifestQuery.isPending)
    return <LoadingRegion label="Préparation du diagnostic" />;
  if (!manifest)
    return (
      <ErrorRegion message={`Le diagnostic ${targetName.toLocaleLowerCase("fr")} n'est pas disponible.`} />
    );

  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow="Étape 3 sur 3"
        title="Point de départ"
        description="Six tâches courtes déterminent si les fondations sont nécessaires avant le premier module."
        action={<StatusPill>{manifest.items.length} tâches</StatusPill>}
      />
      <section className="diagnostic-sheet">
        {manifest.items.map((item: PlacementItemResponse) => (
          <fieldset className="diagnostic-item" key={item.item_revision_id}>
            <legend>
              <span>{item.ordinal}</span>
              {item.prompt}
            </legend>
            {item.choices.length ? (
              item.choices.map((choice) => (
                <label className="choice-row" key={choice.value}>
                  <input
                    checked={answers[item.item_revision_id] === choice.value}
                    name={item.item_revision_id}
                    type="radio"
                    value={choice.value}
                    onChange={() => {
                      setAnswers((current) => ({
                        ...current,
                        [item.item_revision_id]: choice.value,
                      }));
                    }}
                  />
                  <span>{choice.label}</span>
                </label>
              ))
            ) : (
              <label className="answer-field">
                Votre réponse
                <input
                  value={answers[item.item_revision_id] ?? ""}
                  onChange={(event) => {
                    setAnswers((current) => ({
                      ...current,
                      [item.item_revision_id]: event.target.value,
                    }));
                  }}
                />
              </label>
            )}
          </fieldset>
        ))}
        {error ? <ErrorRegion message={error} /> : null}
        <button
          disabled={!allAnswered || busy}
          type="button"
          onClick={() => void finishDiagnostic()}
        >
          {busy ? "Calcul du placement..." : "Terminer le diagnostic"}{" "}
          <ArrowRight aria-hidden="true" size={18} />
        </button>
      </section>
    </div>
  );
}

function FoundationFlow({
  packRevisionId,
  runId,
  onComplete,
  onMissing,
}: {
  packRevisionId: string;
  runId: string;
  onComplete: () => Promise<unknown>;
  onMissing: () => void;
}) {
  const session = useSession();
  const runQuery = useGetFoundationRun(runId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const manifestQuery = useGetFoundationManifest(packRevisionId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [index, setIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [renderedAt] = useState(() => Date.now());
  const run = runQuery.data?.status === 200 ? runQuery.data.data : null;
  const manifest =
    manifestQuery.data?.status === 200 ? manifestQuery.data.data : null;
  const runMissing = runQuery.data?.status === 404;

  useEffect(() => {
    if (runMissing) onMissing();
  }, [onMissing, runMissing]);

  if (runQuery.isPending || manifestQuery.isPending)
    return <LoadingRegion label="Préparation des fondations" />;
  if (runMissing) return <LoadingRegion label="Réinitialisation des fondations" />;
  if (!run || !manifest)
    return (
      <ErrorRegion message="La session de fondations n'est plus disponible." />
    );
  const activity = manifest.activities[index];
  if (!activity)
    return <ErrorRegion message="Le catalogue de fondations est incomplet." />;
  const currentRun = run;
  const currentManifest = manifest;
  const currentActivity = activity;
  const teachingPass = run.session_count === 0;
  const dueAt = new Date(
    new Date(run.started_at).getTime() + 24 * 60 * 60 * 1000,
  );
  const delayedReady = renderedAt >= dueAt.getTime();
  const answer = answers[activity.item_revision_id] ?? "";

  async function advance(value: string) {
    const nextAnswers = {
      ...answers,
      [currentActivity.item_revision_id]: value,
    };
    setAnswers(nextAnswers);
    if (index + 1 < currentManifest.activities.length) {
      setIndex(index + 1);
      return;
    }
    setBusy(true);
    setError("");
    const response = await completeFoundationGate(
      runId,
      {
        answers: currentManifest.activities.map((item) => ({
          item_revision_id: item.item_revision_id,
          answer: { value: nextAnswers[item.item_revision_id] ?? "" },
          revealed: teachingPass,
        })),
      },
      commandFetch(session, currentRun.version),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      setBusy(false);
      return;
    }
    if (response.status !== 200) {
      setError("Le contrôle n'a pas pu être enregistré.");
      setBusy(false);
      return;
    }
    setAnswers({});
    setIndex(0);
    await runQuery.refetch();
    if (response.data.gate_passed) {
      localStorage.removeItem("polyglot.foundation-run");
      await onComplete();
    }
    setBusy(false);
  }

  if (!teachingPass && !delayedReady) {
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow="Fondations italiennes"
          title="Contrôle différé à J+1"
          description="La première session est enregistrée. Le second passage reste fermé pendant 24 heures pour mesurer un rappel réel."
        />
        <section className="onboarding-panel">
          <Milestone aria-hidden="true" size={28} />
          <h2>
            Revenez après{" "}
            {dueAt.toLocaleString("fr-FR", {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </h2>
          <p>Aucun crédit n'est attribué avant ce contrôle sans révélation.</p>
        </section>
      </div>
    );
  }

  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow={teachingPass ? "Apprentissage guidé" : "Contrôle différé"}
        title={activity.block_title}
        description={`${String(index + 1)} sur ${String(manifest.activities.length)} · ${activity.modality}`}
        action={<StatusPill>{activity.block_code}</StatusPill>}
      />
      <section className="foundation-activity">
        <p>{activity.prompt}</p>
        {teachingPass ? (
          <div className="teaching-value">
            <span>Forme à mémoriser</span>
            <strong lang="it">
              {activity.teaching_value?.replaceAll("_", " ") ??
                "Répétez à voix haute"}
            </strong>
          </div>
        ) : activity.choices.length ? (
          <div className="choice-grid">
            {activity.choices.map((choice) => (
              <label className="choice-row" key={choice.value}>
                <input
                  checked={answer === choice.value}
                  name={activity.item_revision_id}
                  type="radio"
                  onChange={() => {
                    setAnswers((current) => ({
                      ...current,
                      [activity.item_revision_id]: choice.value,
                    }));
                  }}
                />
                <span>{choice.label}</span>
              </label>
            ))}
          </div>
        ) : (
          <label className="answer-field">
            Votre réponse
            <input
              autoFocus
              value={answer}
              onChange={(event) => {
                setAnswers((current) => ({
                  ...current,
                  [activity.item_revision_id]: event.target.value,
                }));
              }}
            />
          </label>
        )}
        {error ? <ErrorRegion message={error} /> : null}
        <button
          disabled={
            busy ||
            (!teachingPass &&
              activity.teaching_value !== null &&
              !answer.trim())
          }
          type="button"
          onClick={() =>
            void advance(
              teachingPass
                ? (activity.teaching_value ?? "oral_acknowledged")
                : answer,
            )
          }
        >
          {index + 1 === manifest.activities.length
            ? "Enregistrer la session"
            : teachingPass
              ? "Mémorisé, continuer"
              : "Valider et continuer"}{" "}
          <ArrowRight aria-hidden="true" size={18} />
        </button>
      </section>
    </div>
  );
}
