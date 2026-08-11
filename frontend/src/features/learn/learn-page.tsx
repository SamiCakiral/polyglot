import { ArrowRight, CalendarRange, Route } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import {
  ErrorRegion,
  LoadingRegion,
  PageHeader,
  StatusPill,
} from "../../components/product-ui";
import { useListLearningModules } from "../../generated/polyglot";
import { queryFetch } from "../../lib/api";
import { modulePresentation } from "./module-presentation";

export function LearnPage() {
  const query = useListLearningModules({
    fetch: queryFetch(),
    query: { retry: false },
  });
  if (query.isPending) return <LoadingRegion label="Chargement des modules" />;
  const modules = query.data?.status === 200 ? query.data.data : [];

  return (
    <div className="page-flow">
      <PageHeader
        eyebrow="Curriculum italien"
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
              Le catalogue est prêt, mais aucun parcours italien n'est encore
              disponible.
            </p>
          </section>
        ) : null}
      </div>
    </div>
  );
}

export function ModuleDetailPage() {
  const { moduleId = "" } = useParams();
  const query = useListLearningModules({
    fetch: queryFetch(),
    query: { retry: false },
  });
  if (query.isPending) return <LoadingRegion label="Ouverture du module" />;
  const modules = query.data?.status === 200 ? query.data.data : [];
  const module = modules.find((item) => item.module_id === moduleId);
  if (!module)
    return (
      <div className="page-flow page-flow--narrow">
        <PageHeader
          eyebrow="Module italien"
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
  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow="Module italien"
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
      <Link className="button-link" to="/today">
        Préparer la séance
      </Link>
    </div>
  );
}
