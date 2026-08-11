import { ArrowRight, CalendarRange, Route } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useActiveProfile } from "../../app/profile-state";
import { useSession } from "../../app/session-context";
import {
  ErrorRegion,
  LoadingRegion,
  PageHeader,
  StatusPill,
} from "../../components/product-ui";
import {
  useEnrollInModule,
  useListLearningModules,
} from "../../generated/polyglot";
import {
  commandFetch,
  queryFetch,
  responseProblem,
  todayIso,
} from "../../lib/api";
import { uuid7 } from "../../lib/ids";
import { modulePresentation } from "./module-presentation";

export function LearnPage() {
  const { activePack } = useActiveProfile();
  const query = useListLearningModules(
    activePack
      ? { pack_revision_id: activePack.pack_revision_id }
      : undefined,
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activePack), retry: false },
    },
  );
  if (activePack && query.isPending)
    return <LoadingRegion label="Chargement des modules" />;
  const modules = query.data?.status === 200 ? query.data.data : [];

  return (
    <div className="page-flow">
      <PageHeader
        eyebrow={
          activePack
            ? `Curriculum · ${activePack.target_language_tag}`
            : "Curriculum"
        }
        title="Apprendre"
        description="Des missions cohérentes sur plusieurs jours, reliées au vocabulaire et aux structures à consolider."
      />
      {query.data && query.data.status !== 200 ? (
        <ErrorRegion message="Le catalogue des modules n'est pas disponible." />
      ) : null}
      <div className="module-list">
        {modules.map((module, index) => {
          const presentation = modulePresentation(
            module.module_code,
            module.primary_intention,
          );
          return <article className="module-row" key={module.module_id}>
            <div className="module-row__index">
              {String(index + 1).padStart(2, "0")}
            </div>
            <div className="module-row__body">
              <div>
                <p className="eyebrow">Mission {index + 1}</p>
                <h2>{presentation.title}</h2>
              </div>
              <p>
                Un fil de {module.nominal_days} jours, adaptable entre{" "}
                {module.min_minutes} et {module.max_minutes} minutes par séance.
              </p>
              <div className="module-row__meta">
                <span>
                  <CalendarRange aria-hidden="true" size={17} />{" "}
                  {module.nominal_days} jours
                </span>
                <span>
                  <Route aria-hidden="true" size={17} /> parcours guidé
                </span>
                <StatusPill tone={index === 0 ? "good" : "neutral"}>
                  {index === 0 ? "Disponible" : "À venir"}
                </StatusPill>
              </div>
            </div>
            <Link
              aria-label={`Ouvrir ${presentation.title}`}
              className="icon-link"
              to={`/learn/modules/${module.module_id}`}
            >
              <ArrowRight aria-hidden="true" />
            </Link>
          </article>;
        })}
        {modules.length === 0 ? (
          <section className="empty-panel">
            <h2>Aucun module publié</h2>
            <p>
              Le catalogue est prêt, mais aucun parcours n'est encore
              disponible pour cette langue.
            </p>
          </section>
        ) : null}
      </div>
    </div>
  );
}

export function ModuleDetailPage() {
  const { moduleId = "" } = useParams();
  const { activePack, activeProfile } = useActiveProfile();
  const session = useSession();
  const [error, setError] = useState("");
  const enroll = useEnrollInModule({ fetch: commandFetch(session) });
  const moduleEyebrow = activePack
    ? `Module · ${activePack.target_language_tag}`
    : "Module";
  const query = useListLearningModules(
    activePack
      ? { pack_revision_id: activePack.pack_revision_id }
      : undefined,
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activePack), retry: false },
    },
  );
  if (activePack && query.isPending)
    return <LoadingRegion label="Ouverture du module" />;
  const modules = query.data?.status === 200 ? query.data.data : [];
  const module = modules.find((item) => item.module_id === moduleId);
  if (!module)
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow={moduleEyebrow}
          title="Module indisponible"
          description="Ce module n'existe pas dans la révision publiée du catalogue."
        />
        <ErrorRegion message="Ce module n'est pas disponible." />
        <Link className="text-link" to="/learn">
          Retour aux modules
        </Link>
      </div>
    );
  const presentation = modulePresentation(
    module.module_code,
    module.primary_intention,
  );
  const moduleRevisionId = module.module_revision_id;

  async function beginModule() {
    if (!activeProfile) return;
    setError("");
    const response = await enroll.mutateAsync({
      profileId: activeProfile.profile_id,
      data: {
        enrollment_id: uuid7(),
        module_revision_id: moduleRevisionId,
        pedagogical_day: todayIso(),
        waiver_refs: [],
      },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    window.location.assign("/today");
  }
  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow={moduleEyebrow}
        title={presentation.title}
        description={presentation.description}
        action={<StatusPill tone="good">Publié</StatusPill>}
      />
      <section className="module-brief">
        <div>
          <CalendarRange aria-hidden="true" />
          <strong>{module.nominal_days} jours</strong>
          <span>
            entre {module.min_minutes} et {module.max_minutes} minutes par
            séance
          </span>
        </div>
        <div>
          <Route aria-hidden="true" />
          <strong>Parcours adaptatif</strong>
          <span>
            les rappels, la grammaire et les productions restent liés au même
            fil
          </span>
        </div>
      </section>
      {error ? <ErrorRegion message={error} /> : null}
      <button
        disabled={!activeProfile || enroll.isPending}
        type="button"
        onClick={() => void beginModule()}
      >
        {enroll.isPending ? "Inscription..." : "Commencer ce module"}
        <ArrowRight aria-hidden="true" size={18} />
      </button>
    </div>
  );
}
