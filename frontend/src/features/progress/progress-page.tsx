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
import type { MasteryFacetResponse } from "../../generated/model";
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

const assessmentBandLabels: Record<string, string> = {
  assess_b0: "Palier 0",
  assess_b1: "Palier 1",
  assess_b2: "Palier 2",
  assess_b3: "Palier 3",
  assess_b4: "Palier 4",
};

const operationLabels: Record<string, string> = {
  interact: "Interagir à l'oral",
  produce: "Produire",
  recall: "Rappeler activement",
  recognize: "Reconnaître",
  repair: "Corriger",
  transform: "Transformer",
};

function aggregateFacets(
  facets: MasteryFacetResponse[],
): MasteryFacetResponse[] {
  const grouped = new Map<string, MasteryFacetResponse[]>();
  for (const facet of facets) {
    const key = `${facet.facet_key}:${facet.modality}:${facet.operation}`;
    grouped.set(key, [...(grouped.get(key) ?? []), facet]);
  }
  return [...grouped.values()].flatMap((items) => {
    const first = items[0];
    if (!first) return [];
    const totalMass = items.reduce((sum, item) => sum + item.effective_mass, 0);
    const weighted = (field: "mastery_base" | "mastery_current" | "confidence" | "freshness") =>
      items.reduce(
        (sum, item) =>
          sum + item[field] * (totalMass > 0 ? item.effective_mass : 1),
        0,
      ) / (totalMass > 0 ? totalMass : items.length);
    return [{
      ...first,
      confidence: weighted("confidence"),
      context_count: items.reduce((sum, item) => sum + item.context_count, 0),
      delay_band_count: items.reduce(
        (sum, item) => sum + item.delay_band_count,
        0,
      ),
      effective_mass: totalMass,
      evidence_ids: [...new Set(items.flatMap((item) => item.evidence_ids))],
      failure_count: items.reduce((sum, item) => sum + item.failure_count, 0),
      freshness: weighted("freshness"),
      mastery_base: weighted("mastery_base"),
      mastery_current: weighted("mastery_current"),
      session_count: items.reduce((sum, item) => sum + item.session_count, 0),
      success_count: items.reduce((sum, item) => sum + item.success_count, 0),
      target_id: first.facet_key,
      target_type: "compétence agrégée",
      transfer_count: items.reduce((sum, item) => sum + item.transfer_count, 0),
    }];
  });
}

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
  const facets = aggregateFacets(overview?.facets ?? []);
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
              {modality.assessment_status ? (
                <div className="assessment-calibration">
                  <span>Dernier test indépendant</span>
                  {modality.assessment_status === "not_evaluable" ? (
                    <strong>Non évaluable</strong>
                  ) : (
                    <strong>
                      {Math.round((modality.assessment_score ?? 0) * 100)} / 100
                      {modality.assessment_band
                        ? ` · ${assessmentBandLabels[modality.assessment_band] ?? modality.assessment_band}`
                        : ""}
                    </strong>
                  )}
                  {modality.assessment_confidence !== null ? (
                    <small>
                      Confiance du test{" "}
                      {Math.round((modality.assessment_confidence ?? 0) * 100)} %
                    </small>
                  ) : null}
                </div>
              ) : null}
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
          <span>{facets.length} compétences</span>
        </div>
        <div className="skill-ledger__rows">
          {facets.slice(0, 12).map((facet) => (
            <div
              key={`${facet.facet_key}:${facet.modality}:${facet.operation}`}
            >
              <span>
                <Link
                  to={`/progress/skills/${encodeURIComponent(facet.facet_key)}`}
                >
                  <strong>
                    {operationLabels[facet.operation] ??
                      facet.operation.replaceAll("_", " ")}
                  </strong>
                </Link>
                <small>
                  {modalityMeta[facet.modality]?.label ?? facet.modality} ·{" "}
                  {facet.context_count} contexte
                  {facet.context_count > 1 ? "s" : ""}
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
  const facet = aggregateFacets(overview?.facets ?? []).find(
    (item) => item.facet_key === skillId,
  );

  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow="Preuves de progression"
        title={
          (facet
            ? operationLabels[facet.operation] ??
              facet.operation.replaceAll("_", " ")
            : null) ?? "Détail de la compétence"
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
