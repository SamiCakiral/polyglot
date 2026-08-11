import { ArrowLeft, Ear, Eye, Mic2, PenLine } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { useActiveProfile } from "../../app/profile-state";
import {
  ErrorRegion,
  LoadingRegion,
  Meter,
  NoProfile,
  PageHeader,
  StatusPill,
} from "../../components/product-ui";
import { useGetProgressOverview } from "../../generated/polyglot";
import { queryFetch } from "../../lib/api";

const modalityMeta: Record<string, { label: string; icon: typeof Eye }> = {
  reading: { label: "Compréhension écrite", icon: Eye },
  listening: { label: "Compréhension orale", icon: Ear },
  writing: { label: "Expression écrite", icon: PenLine },
  speaking: { label: "Expression orale", icon: Mic2 },
};

const statusLabels: Record<string, string> = {
  non_observed: "Non observé",
  discovered: "Découvert",
  in_progress: "En cours",
  reliable: "Fiable",
  mastered: "Maîtrisé",
  review_due: "À revoir",
  not_evaluable: "Non évaluable",
};

export function ProgressPage() {
  const { activeProfile } = useActiveProfile();
  const query = useGetProgressOverview(
    activeProfile?.profile_id ?? "",
    { limit: 100 },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activeProfile), retry: false },
    },
  );
  const overview = query.data?.status === 200 ? query.data.data : null;
  if (!activeProfile) return <NoProfile />;
  if (query.isPending)
    return <LoadingRegion label="Calcul de la progression" />;

  return (
    <div className="page-flow">
      <PageHeader
        eyebrow="État des preuves"
        title="Progression"
        description="Quatre compétences séparées. La confiance et la couverture indiquent ce que le système sait réellement."
      />
      {query.data && query.data.status !== 200 ? (
        <ErrorRegion message="La projection de progression n'est pas disponible." />
      ) : null}
      <div className="modality-grid">
        {(overview?.modalities ?? []).map((modality) => {
          const meta = modalityMeta[modality.modality] ?? {
            label: modality.modality,
            icon: Eye,
          };
          const Icon = meta.icon;
          return (
            <article className="modality-panel" key={modality.modality}>
              <div className="modality-panel__header">
                <Icon aria-hidden="true" />
                <div>
                  <h2>{meta.label}</h2>
                  <StatusPill
                    tone={
                      modality.status === "mastered" ||
                      modality.status === "reliable"
                        ? "good"
                        : modality.status === "review_due"
                          ? "warn"
                          : "neutral"
                    }
                  >
                    {statusLabels[modality.status] ?? modality.status}
                  </StatusPill>
                </div>
              </div>
              {modality.score === null ? (
                <p className="unknown-score">
                  Pas encore assez de preuves pour afficher un niveau.
                </p>
              ) : (
                <div className="score-display">
                  <strong>{Math.round(modality.score * 100)}</strong>
                  <span>/ 100</span>
                </div>
              )}
              <Meter label="Confiance" value={modality.confidence} />
              <Meter label="Couverture" value={modality.coverage} />
              <small>
                {modality.observed_facet_count} compétences observées sur{" "}
                {modality.expected_facet_count}
              </small>
            </article>
          );
        })}
      </div>
      <section className="skill-ledger">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Compétences observées</p>
            <h2>Détail des acquis</h2>
          </div>
          <span>{overview?.facets.length ?? 0} facettes</span>
        </div>
        <div className="skill-ledger__rows">
          {(overview?.facets ?? []).slice(0, 12).map((facet) => (
            <div key={facet.facet_key}>
              <span>
                <Link
                  to={`/progress/skills/${encodeURIComponent(facet.facet_key)}`}
                >
                  <strong>{facet.operation.replaceAll("_", " ")}</strong>
                </Link>
                <small>
                  {modalityMeta[facet.modality]?.label ?? facet.modality} ·{" "}
                  {facet.context_count} contextes
                </small>
              </span>
              <Meter label="Maîtrise actuelle" value={facet.mastery_current} />
              <StatusPill
                tone={
                  facet.status === "mastered" || facet.status === "reliable"
                    ? "good"
                    : facet.status === "review_due"
                      ? "warn"
                      : "neutral"
                }
              >
                {statusLabels[facet.status] ?? facet.status}
              </StatusPill>
            </div>
          ))}
        </div>
      </section>
      {overview?.modalities.length === 0 ? (
        <section className="empty-panel">
          <h2>Aucune preuve pour le moment</h2>
          <p>
            Une première séance ou un diagnostic fera apparaître les quatre axes
            ici.
          </p>
        </section>
      ) : null}
    </div>
  );
}

export function ProgressSkillDetailPage() {
  const { skillId = "" } = useParams();
  const { activeProfile } = useActiveProfile();
  const query = useGetProgressOverview(
    activeProfile?.profile_id ?? "",
    { limit: 500 },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activeProfile), retry: false },
    },
  );
  if (!activeProfile) return <NoProfile />;
  if (query.isPending)
    return <LoadingRegion label="Ouverture de la compétence" />;
  const overview = query.data?.status === 200 ? query.data.data : null;
  const facet = overview?.facets.find((item) => item.facet_key === skillId);

  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow="Preuves de progression"
        title={
          facet?.operation.replaceAll("_", " ") ?? "Détail de la compétence"
        }
        description={
          facet
            ? `${modalityMeta[facet.modality]?.label ?? facet.modality} · ${facet.target_type}`
            : "Cette facette n'a pas encore de preuve dans la projection active."
        }
        action={
          facet ? (
            <StatusPill
              tone={
                facet.status === "mastered" || facet.status === "reliable"
                  ? "good"
                  : facet.status === "review_due"
                    ? "warn"
                    : "neutral"
              }
            >
              {statusLabels[facet.status] ?? facet.status}
            </StatusPill>
          ) : null
        }
      />
      {query.data && query.data.status !== 200 ? (
        <ErrorRegion message="La projection de progression n'est pas disponible." />
      ) : null}
      {facet ? (
        <section className="skill-evidence-detail">
          <Meter label="Maîtrise actuelle" value={facet.mastery_current} />
          <Meter label="Confiance" value={facet.confidence} />
          <Meter label="Fraîcheur" value={facet.freshness} />
          <dl>
            <div>
              <dt>Réussites</dt>
              <dd>{facet.success_count}</dd>
            </div>
            <div>
              <dt>Échecs</dt>
              <dd>{facet.failure_count}</dd>
            </div>
            <div>
              <dt>Contextes</dt>
              <dd>{facet.context_count}</dd>
            </div>
            <div>
              <dt>Transferts</dt>
              <dd>{facet.transfer_count}</dd>
            </div>
            <div>
              <dt>Séances</dt>
              <dd>{facet.session_count}</dd>
            </div>
            <div>
              <dt>Preuves</dt>
              <dd>{facet.evidence_ids.length}</dd>
            </div>
          </dl>
        </section>
      ) : (
        <section className="empty-panel">
          <h2>Compétence non observée</h2>
          <p>
            Elle apparaîtra ici dès qu'une preuve éligible aura été enregistrée.
          </p>
        </section>
      )}
      <Link className="text-link" to="/progress">
        <ArrowLeft aria-hidden="true" size={17} /> Retour à la progression
      </Link>
    </div>
  );
}
