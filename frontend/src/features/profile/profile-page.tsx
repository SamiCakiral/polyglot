import {
  ArrowRight,
  Check,
  Dumbbell,
  Languages,
  Milestone,
} from "lucide-react";
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
import type {
  EntryPath,
  PlacementChoice,
  PlacementItemResponse,
} from "../../generated/model";
import {
  choosePlacement,
  completeDiagnostic,
  completeFoundationGate,
  createAccountLanguage,
  enrollInModule,
  getDiagnosticSummary,
  startDiagnostic,
  startFoundationRun,
  startOnboarding,
  submitDiagnosticResponse,
  useCreateLanguageProfile,
  useGetFoundationManifest,
  useGetFoundationRun,
  useGetOnboardingState,
  useGetPlacementManifest,
  useListAccountLanguages,
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

const entryPaths: {
  value: EntryPath;
  title: string;
  description: string;
  duration: string;
}[] = [
  {
    value: "complete_beginner",
    title: "Je pars de zéro",
    description:
      "Commencer par les sons, l'écriture et les premiers moules utiles.",
    duration: "entraînement immédiat",
  },
  {
    value: "already_started",
    title: "J'ai déjà commencé",
    description:
      "Faire six tâches courtes pour retrouver un point de départ crédible.",
    duration: "5 à 8 minutes",
  },
  {
    value: "advanced",
    title: "Je suis déjà autonome",
    description:
      "Commencer plus haut et chercher rapidement les zones fragiles.",
    duration: "8 à 10 minutes",
  },
];

const skillLabels: Record<string, string> = {
  script: "Écriture et sons",
  reading: "Lecture",
  listening: "Écoute",
  vocabulary: "Vocabulaire",
  production: "Production",
  grammar_functions: "Moules grammaticaux",
};

const bandLabels: Record<string, string> = {
  foundations: "Fondations",
  emerging: "En construction",
  functional: "Fonctionnel",
  independent: "Autonome",
  advanced: "Avancé",
};

export function LanguageProfilePage() {
  const session = useSession();
  const navigate = useNavigate();
  const {
    activeProfile,
    isPending,
    profiles,
    refresh,
    selectProfile,
  } = useActiveProfile();
  const [creatingAdditionalProfile, setCreatingAdditionalProfile] =
    useState(false);
  const [selectedPackRevisionId, setSelectedPackRevisionId] = useState("");
  const packsQuery = useListLanguagePacks(
    { limit: 20 },
    { fetch: queryFetch(), query: { retry: false } },
  );
  const accountLanguagesQuery = useListAccountLanguages({
    fetch: queryFetch(),
    query: { retry: false },
  });
  const packs =
    packsQuery.data?.status === 200 ? packsQuery.data.data.items : [];
  const availablePacks = packs.filter(
    (item) =>
      !profiles.some(
        (profile) => profile.target_variety_id === item.target_variety_id,
      ),
  );
  const creationPacks = activeProfile ? availablePacks : packs;
  const pack = creatingAdditionalProfile
    ? (creationPacks.find(
        (item) => item.pack_revision_id === selectedPackRevisionId,
      ) ?? creationPacks[0])
    : activeProfile
      ? packs.find(
        (item) => item.target_variety_id === activeProfile.target_variety_id,
      )
      : (creationPacks.find(
          (item) => item.pack_revision_id === selectedPackRevisionId,
        ) ?? creationPacks[0]);
  const modulesQuery = useListLearningModules(
    pack ? { pack_revision_id: pack.pack_revision_id } : undefined,
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(pack), retry: false },
    },
  );
  const displayNames = new Intl.DisplayNames(["fr"], { type: "language" });
  const targetName = pack
    ? (displayNames.of(new Intl.Locale(pack.target_language_tag).language) ??
      pack.target_language_tag)
    : "la langue cible";
  const supportName = pack?.support_language_tags[0]
    ? (displayNames.of(
        new Intl.Locale(pack.support_language_tags[0]).language,
      ) ??
      pack.support_language_tags[0])
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
  const onboardingQuery = useGetOnboardingState(
    activeProfile?.profile_id ?? "",
    {
      fetch: queryFetch(),
      query: {
        enabled: Boolean(activeProfile && activeProfile.goals.length > 0),
        retry: false,
      },
    },
  );
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
  const [supportRelationship, setSupportRelationship] = useState<
    "native" | "fluent" | "studied"
  >("native");

  const manifest =
    manifestQuery.data?.status === 200 ? manifestQuery.data.data : null;
  const modules =
    modulesQuery.data?.status === 200 ? modulesQuery.data.data : [];
  const accountLanguages =
    accountLanguagesQuery.data?.status === 200
      ? accountLanguagesQuery.data.data.items
      : [];
  const onboarding =
    onboardingQuery.data?.status === 200 ? onboardingQuery.data.data : null;
  const onboardingMissing = onboardingQuery.data?.status === 404;
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
    if (
      !accountLanguages.some(
        (item) => item.variety_id === pack.support_variety_ids[0],
      )
    ) {
      const declared = await createAccountLanguage(
        {
          variety_id: pack.support_variety_ids[0],
          relationship: supportRelationship,
          self_assessed_band:
            supportRelationship === "studied" ? "independent" : "advanced",
          use_for_explanations: true,
          use_for_contrasts: true,
        },
        commandFetch(session),
      );
      const declarationProblem = responseProblem(declared);
      if (declarationProblem) {
        setError(declarationProblem);
        return;
      }
    }
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
    await accountLanguagesQuery.refetch();
    if (response.status === 201) {
      selectProfile(response.data.profile_id);
      setCreatingAdditionalProfile(false);
      setSelectedPackRevisionId("");
    }
  }

  async function chooseEntryPath(entryPath: EntryPath) {
    if (!activeProfile || !pack) return;
    setBusy(true);
    setError("");
    try {
      if (
        !accountLanguages.some(
          (item) => item.variety_id === pack.target_variety_id,
        )
      ) {
        const targetLanguage = await createAccountLanguage(
          {
            variety_id: pack.target_variety_id,
            relationship: "studied",
            self_assessed_band:
              entryPath === "complete_beginner"
                ? "new"
                : entryPath === "advanced"
                  ? "independent"
                  : "familiar",
            use_for_explanations: false,
            use_for_contrasts: false,
          },
          commandFetch(session),
        );
        const targetProblem = responseProblem(targetLanguage);
        if (targetProblem) throw new Error(targetProblem);
      }
      const started = await startOnboarding(
        activeProfile.profile_id,
        { entry_path: entryPath },
        commandFetch(session),
      );
      const startProblem = responseProblem(started);
      if (startProblem || started.status !== 200) {
        throw new Error(
          startProblem || "Le point de départ n'a pas été enregistré.",
        );
      }
      if (entryPath === "complete_beginner") {
        const chosen = await choosePlacement(
          activeProfile.profile_id,
          { choice: "start_now" },
          commandFetch(session, started.data.version),
        );
        const choiceProblem = responseProblem(chosen);
        if (choiceProblem) throw new Error(choiceProblem);
        await refresh();
        void navigate("/practice");
        return;
      }
      await onboardingQuery.refetch();
      await accountLanguagesQuery.refetch();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "L'onboarding n'a pas pu démarrer.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function acceptPlacement(choice: PlacementChoice) {
    if (!activeProfile || !onboarding) return;
    setBusy(true);
    setError("");
    try {
      const response = await choosePlacement(
        activeProfile.profile_id,
        { choice },
        commandFetch(session, onboarding.version),
      );
      const problem = responseProblem(response);
      if (problem) throw new Error(problem);
      await refresh();
      void navigate("/practice");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Le choix n'a pas été enregistré.",
      );
    } finally {
      setBusy(false);
    }
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
      throw new Error(
        `Aucun module ${targetName.toLocaleLowerCase("fr")} publié n'est disponible.`,
      );
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
      await onboardingQuery.refetch();
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

  if (!pack && !creatingAdditionalProfile) {
    return (
      <ErrorRegion message="Aucun parcours linguistique n'est publié sur cette installation." />
    );
  }

  if (!activeProfile || creatingAdditionalProfile) {
    if (!pack) {
      return (
        <div className="page-flow page-flow--narrow">
          <PageHeader
            eyebrow="Parcours linguistiques"
            title="Toutes les langues publiées sont déjà configurées"
            description="Utilisez le sélecteur de langue pour reprendre un parcours existant."
          />
          <button
            className="secondary-button"
            type="button"
            onClick={() => {
              setCreatingAdditionalProfile(false);
            }}
          >
            Retour au profil actif
          </button>
        </div>
      );
    }
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow={activeProfile ? "Nouveau parcours" : "Étape 1 sur 3"}
          title={activeProfile ? "Ajouter une langue" : "Votre profil de langue"}
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
              {creationPacks.map((item) => (
                <option
                  key={item.pack_revision_id}
                  value={item.pack_revision_id}
                >
                  {displayNames.of(item.support_language_tags[0] ?? "") ??
                    item.support_language_tags[0]}
                  {" → "}
                  {displayNames.of(item.target_language_tag) ??
                    item.target_language_tag}
                </option>
              ))}
            </select>
          </label>
          <label className="answer-field">
            Votre rapport avec {supportName}
            <select
              value={supportRelationship}
              onChange={(event) => {
                setSupportRelationship(
                  event.target.value as "native" | "fluent" | "studied",
                );
              }}
            >
              <option value="native">Langue maternelle</option>
              <option value="fluent">Parlée couramment</option>
              <option value="studied">Apprise et bien comprise</option>
            </select>
          </label>
          <div
            className="language-pair"
            aria-label={`${supportName} vers ${targetName}`}
          >
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
            Les explications utilisent {supportName.toLocaleLowerCase("fr")} et
            les activités travaillent {targetName.toLocaleLowerCase("fr")}.
          </p>
          {error ? <ErrorRegion message={error} /> : null}
          <button disabled={createProfile.isPending} type="submit">
            {createProfile.isPending ? "Création..." : "Créer ce profil"}
          </button>
          {activeProfile ? (
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setCreatingAdditionalProfile(false);
                setError("");
              }}
            >
              Annuler
            </button>
          ) : null}
        </form>
      </div>
    );
  }

  if (!pack) {
    return (
      <ErrorRegion message="Le parcours actif n'existe plus dans le catalogue publié." />
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

  if (onboardingQuery.isPending) {
    return <LoadingRegion label="Chargement de votre point de départ" />;
  }

  if (onboardingMissing) {
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow="Point de départ"
          title={`Où en êtes-vous en ${targetName.toLocaleLowerCase("fr")} ?`}
          description="Choisissez l'option la plus proche. Rien ne vous empêchera de vous entraîner ensuite."
        />
        <section
          className="entry-paths"
          aria-label="Choisir un point de départ"
        >
          {entryPaths.map((entry) => (
            <button
              className="entry-path"
              disabled={busy}
              key={entry.value}
              type="button"
              onClick={() => void chooseEntryPath(entry.value)}
            >
              <span>
                <strong>{entry.title}</strong>
                <small>{entry.duration}</small>
              </span>
              <p>{entry.description}</p>
              <ArrowRight aria-hidden="true" size={19} />
            </button>
          ))}
        </section>
        {error ? <ErrorRegion message={error} /> : null}
      </div>
    );
  }

  if (onboarding?.detected_band && !onboarding.placement_choice) {
    const confidence = Math.round((onboarding.placement_confidence ?? 0) * 100);
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow="Placement terminé"
          title={`Point de départ : ${bandLabels[onboarding.detected_band] ?? onboarding.detected_band}`}
          description="Cette estimation décrit vos preuves actuelles. Vous gardez le dernier mot sur le niveau de départ."
          action={<StatusPill>{confidence}% de confiance</StatusPill>}
        />
        <section className="placement-result">
          <div className="placement-summary">
            <Milestone aria-hidden="true" size={24} />
            <div>
              <strong>{bandLabels[onboarding.resolved_band]}</strong>
              <span>Trois premières séances continueront la calibration.</span>
            </div>
          </div>
          <div
            className="skill-map"
            aria-label="Carte des compétences détectées"
            role="region"
          >
            {onboarding.skill_profile.map((skill) => (
              <div className="skill-line" key={skill.dimension}>
                <span>{skillLabels[skill.dimension]}</span>
                <strong>{bandLabels[skill.band]}</strong>
                <small>
                  {skill.evidence_count > 0
                    ? `${String(Math.round(skill.confidence * 100))}% de confiance`
                    : "à calibrer"}
                </small>
              </div>
            ))}
          </div>
          <div
            className="placement-actions"
            aria-label="Ajuster le niveau de départ"
          >
            <button
              className="secondary-button"
              disabled={busy}
              type="button"
              onClick={() => void acceptPlacement("start_easier")}
            >
              Commencer plus doucement
            </button>
            <button
              disabled={busy}
              type="button"
              onClick={() => void acceptPlacement("accept")}
            >
              Accepter et s'entraîner <Dumbbell aria-hidden="true" size={18} />
            </button>
            <button
              className="secondary-button"
              disabled={busy}
              type="button"
              onClick={() => void acceptPlacement("challenge")}
            >
              Me mettre au défi
            </button>
          </div>
          {error ? <ErrorRegion message={error} /> : null}
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
          targetLanguageTag={pack.target_language_tag}
          targetName={targetName}
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
          action={
            availablePacks.length > 0 ? (
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setSelectedPackRevisionId(
                    availablePacks[0]?.pack_revision_id ?? "",
                  );
                  setCreatingAdditionalProfile(true);
                }}
              >
                Ajouter une langue
              </button>
            ) : undefined
          }
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
      <ErrorRegion
        message={`Le diagnostic ${targetName.toLocaleLowerCase("fr")} n'est pas disponible.`}
      />
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
  targetLanguageTag,
  targetName,
  onComplete,
  onMissing,
}: {
  packRevisionId: string;
  runId: string;
  targetLanguageTag: string;
  targetName: string;
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
  if (runMissing)
    return <LoadingRegion label="Réinitialisation des fondations" />;
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
          eyebrow={`Fondations ${targetName.toLocaleLowerCase("fr")}`}
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
            <strong lang={targetLanguageTag}>
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
