import {
  Braces,
  CheckCircle2,
  FileClock,
  Play,
  Plus,
  ShieldAlert,
  Sparkles,
  Wrench,
} from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useSession } from "../../app/session-context";
import {
  ErrorRegion,
  LoadingRegion,
  PageHeader,
  StatusPill,
} from "../../components/product-ui";
import type {
  ContentRevisionResponse,
  JsonValueInput,
  ToolDefinitionResponse,
} from "../../generated/model";
import {
  approveContentRevision,
  createContentDraft,
  publishContentRevision,
  requestGenerationJob,
  retireContentRevision,
  reviseContentDraft,
  useInvokeAuthoringTool,
  useGetGenerationJob,
  useListAuthoringArtifacts,
  useListAuthoringTools,
  useListContentDrafts,
  useListLanguagePacks,
  validateContentRevision,
} from "../../generated/polyglot";
import { commandFetch, queryFetch, responseProblem } from "../../lib/api";
import { uuid7 } from "../../lib/ids";

function AuthorGuard({ children }: { children: ReactNode }) {
  const session = useSession();
  const allowed = session.roles.some((role) =>
    ["author", "reviewer", "admin"].includes(role),
  );
  if (!allowed) {
    return (
      <div className="page-flow page-flow--narrow">
        <section className="forbidden-panel" role="alert">
          <ShieldAlert aria-hidden="true" />
          <h1>Atelier réservé</h1>
          <p>
            Votre rôle apprenant ne donne accès ni aux brouillons ni aux outils
            éditoriaux.
          </p>
          <Link to="/today">Retour à l'apprentissage</Link>
        </section>
      </div>
    );
  }
  return children;
}

export function AuthoringPage() {
  return (
    <AuthorGuard>
      <div className="page-flow">
        <PageHeader
          eyebrow="Espace éditorial"
          title="Atelier"
          description="Créer, vérifier et publier du contenu italien avec une trace complète des décisions humaines."
        />
        <div className="authoring-launcher">
          <Link to="/authoring/drafts">
            <FileClock aria-hidden="true" />
            <span>
              <strong>Brouillons et révisions</strong>
              <small>
                Comparer les versions, lancer la validation et suivre les
                décisions.
              </small>
            </span>
          </Link>
          <Link to="/authoring/tools">
            <Wrench aria-hidden="true" />
            <span>
              <strong>Outils contrôlés</strong>
              <small>
                Exécuter les contrats déterministes autorisés pour votre rôle.
              </small>
            </span>
          </Link>
          <Link to="/authoring/generate">
            <Sparkles aria-hidden="true" />
            <span>
              <strong>Génération locale</strong>
              <small>
                Préparer un artefact avec LM Studio avant la revue humaine.
              </small>
            </span>
          </Link>
        </div>
        <section className="integrity-note">
          <strong>Publication humaine uniquement</strong>
          <p>
            La génération prépare un brouillon. Elle ne publie rien et ne
            produit aucun crédit de maîtrise.
          </p>
        </section>
      </div>
    </AuthorGuard>
  );
}

const generationKinds = {
  exercise: {
    label: "Exercice",
    taskType: "exercise_draft",
    tool: "exercise.submit_draft@1.0.0",
  },
  module: {
    label: "Module",
    taskType: "module_draft",
    tool: "curriculum.submit_module_draft@1.0.0",
  },
  day: {
    label: "Journée de module",
    taskType: "day_draft",
    tool: "curriculum.submit_day_draft@1.0.0",
  },
  quality: {
    label: "Rapport d'ambiguïté",
    taskType: "quality_report",
    tool: "quality.report_ambiguity@1.0.0",
  },
} as const;

type GenerationKind = keyof typeof generationKinds;

export function GenerationPage() {
  const session = useSession();
  const [kind, setKind] = useState<GenerationKind>("exercise");
  const [brief, setBrief] = useState(
    "Créer un exercice italien sur un trajet en train, niveau débutant, avec une consigne sans ambiguïté.",
  );
  const [jobId, setJobId] = useState("");
  const [adoptedRevisionId, setAdoptedRevisionId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const jobQuery = useGetGenerationJob(jobId, {
    fetch: queryFetch(),
    query: {
      enabled: Boolean(jobId),
      refetchInterval: 1000,
      retry: false,
    },
  });
  const artifactsQuery = useListAuthoringArtifacts(
    { limit: 50 },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(jobId), refetchInterval: 1000, retry: false },
    },
  );
  const packsQuery = useListLanguagePacks(
    { limit: 20 },
    { fetch: queryFetch(), query: { retry: false } },
  );
  const job = jobQuery.data?.status === 200 ? jobQuery.data.data : undefined;
  const artifacts =
    artifactsQuery.data?.status === 200 ? artifactsQuery.data.data : [];
  const artifact = artifacts.find(
    (item) => item.artifact_id === job?.result_draft_id,
  );
  const pack =
    packsQuery.data?.status === 200 ? packsQuery.data.data.items[0] : undefined;

  async function generate() {
    setBusy(true);
    setError("");
    setJobId("");
    const selected = generationKinds[kind];
    try {
      const response = await requestGenerationJob(
        {
          max_attempts: 1,
          max_cost_micros: 1,
          max_input_tokens: 8000,
          max_output_tokens: 6000,
          model_code: "qwen/qwen3.6-35b-a3b",
          prompt_revision: "POLYGLOT_AUTHOR_V1",
          provider_code: "lm_studio",
          task_input: {
            brief,
            support_language: "fr-FR",
            target_language: "it-IT",
          },
          task_type: selected.taskType,
          tool_allowlist: [selected.tool],
        },
        commandFetch(session),
      );
      const problem = responseProblem(response);
      if (problem) throw new Error(problem);
      if (response.status === 201) setJobId(response.data.job_id);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "La génération a échoué.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function adoptArtifact() {
    if (!artifact || !pack) {
      setError("Le pack italien publié est indisponible.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await createContentDraft(
        {
          content_type: artifact.artifact_type,
          pack_id: pack.pack_id,
          payload: {
            ...artifact.payload,
            generation_artifact_id: artifact.artifact_id,
            generation_source_tool: artifact.source_tool_name,
          },
          provenance_id: uuid7(),
          rights_ref: `rights:tool:${artifact.artifact_id}`,
          variety_id: pack.target_variety_id,
        },
        commandFetch(session),
      );
      const problem = responseProblem(response);
      if (problem) throw new Error(problem);
      if (response.status === 201) {
        setAdoptedRevisionId(response.data.content_revision_id);
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "L'adoption du brouillon a échoué.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthorGuard>
      <div className="page-flow page-flow--narrow">
        <PageHeader eyebrow="Atelier local" title="Génération" />
        <section className="generation-workbench">
          <label>
            Type de contenu
            <select
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as GenerationKind);
              }}
            >
              {Object.entries(generationKinds).map(([value, item]) => (
                <option key={value} value={value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Brief
            <textarea
              rows={7}
              value={brief}
              onChange={(event) => {
                setBrief(event.target.value);
              }}
            />
          </label>
          <button
            type="button"
            disabled={busy || !brief.trim()}
            onClick={() => {
              void generate();
            }}
          >
            <Sparkles aria-hidden="true" size={18} />
            {busy ? "Envoi…" : "Générer l'artefact"}
          </button>
        </section>
        {error ? <ErrorRegion message={error} /> : null}
        {job ? (
          <section className="generation-result" aria-live="polite">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Exécution locale</p>
                <h2>Résultat</h2>
              </div>
              <StatusPill
                tone={
                  job.status === "succeeded"
                    ? "good"
                    : job.status === "failed"
                      ? "warn"
                      : "neutral"
                }
              >
                {job.status}
              </StatusPill>
            </div>
            {job.error_code ? (
              <p role="alert">Fournisseur indisponible : {job.error_code}</p>
            ) : null}
            {artifact ? (
              <>
                <p>
                  <strong>{artifact.artifact_type}</strong> · {artifact.source_tool_name}
                </p>
                <pre>{JSON.stringify(artifact.payload, null, 2)}</pre>
                {adoptedRevisionId ? (
                  <p>
                    Brouillon éditorial créé. <Link to="/authoring/drafts">Ouvrir la revue</Link>
                  </p>
                ) : (
                  <button
                    type="button"
                    disabled={busy || !pack}
                    onClick={() => {
                      void adoptArtifact();
                    }}
                  >
                    <CheckCircle2 aria-hidden="true" size={18} />
                    Adopter comme brouillon
                  </button>
                )}
              </>
            ) : null}
          </section>
        ) : null}
      </div>
    </AuthorGuard>
  );
}

export function DraftsPage() {
  const session = useSession();
  const query = useListContentDrafts(
    { limit: 50 },
    { fetch: queryFetch(), query: { retry: false } },
  );
  const packsQuery = useListLanguagePacks(
    { limit: 20 },
    { fetch: queryFetch(), query: { retry: false } },
  );
  const [selected, setSelected] = useState<ContentRevisionResponse | null>(
    null,
  );
  const [payloadText, setPayloadText] = useState(
    '{\n  "title": "Nouvel exercice",\n  "instruction": "Répondez en italien."\n}',
  );
  const [contentType, setContentType] = useState("exercise");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (query.isPending)
    return <LoadingRegion label="Chargement des brouillons" />;
  const drafts = query.data?.status === 200 ? query.data.data.items : [];
  const pack =
    packsQuery.data?.status === 200 ? packsQuery.data.data.items[0] : undefined;
  const canAuthor = session.roles.some((role) =>
    ["author", "admin"].includes(role),
  );
  const canReview = session.roles.some((role) =>
    ["reviewer", "admin"].includes(role),
  );

  function parsePayload(): Record<string, JsonValueInput> {
    const value = JSON.parse(payloadText) as unknown;
    if (!value || Array.isArray(value) || typeof value !== "object")
      throw new Error("Le contenu doit être un objet JSON.");
    return value as Record<string, JsonValueInput>;
  }

  async function run(action: () => Promise<{ status: number; data: unknown }>) {
    setBusy(true);
    setError("");
    try {
      const response = await action();
      const problem = responseProblem(response);
      if (problem) throw new Error(problem);
      if (response.status >= 200 && response.status < 300) {
        const revision = response.data as ContentRevisionResponse;
        setSelected(revision);
        setPayloadText(JSON.stringify(revision.payload, null, 2));
        await query.refetch();
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "L'opération éditoriale a échoué.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function create() {
    if (!pack) {
      setError("Aucun pack publié n'est disponible.");
      return;
    }
    await run(() =>
      createContentDraft(
        {
          content_type: contentType,
          pack_id: pack.pack_id,
          payload: parsePayload(),
          provenance_id: uuid7(),
          rights_ref: "original:polyglot-author",
          variety_id: pack.target_variety_id,
        },
        commandFetch(session),
      ),
    );
  }

  function choose(draft: ContentRevisionResponse) {
    setSelected(draft);
    setPayloadText(JSON.stringify(draft.payload, null, 2));
    setError("");
  }
  const version = selected?.version ?? undefined;

  return (
    <AuthorGuard>
      <div className="page-flow">
        <PageHeader
          eyebrow="Cycle éditorial"
          title="Brouillons"
          description="Les révisions sont immuables ; chaque validation ou décision ajoute une nouvelle trace."
          action={
            canAuthor ? (
              <button
                type="button"
                onClick={() => {
                  setSelected(null);
                  setPayloadText(
                    '{\n  "title": "Nouvel exercice",\n  "instruction": "Répondez en italien."\n}',
                  );
                }}
              >
                <Plus aria-hidden="true" size={18} /> Nouveau
              </button>
            ) : undefined
          }
        />
        <section className="editorial-workbench">
          <div className="data-table author-table" role="table">
            <div className="data-table__head" role="row">
              <span>Contenu</span>
              <span>Révision</span>
              <span>État</span>
              <span>Créé le</span>
            </div>
            {drafts.map((draft) => (
              <button
                className="data-table__row"
                role="row"
                key={draft.content_revision_id}
                type="button"
                onClick={() => {
                  choose(draft);
                }}
              >
                <span>
                  <strong>{draft.content_id}</strong>
                  <small>{draft.payload_checksum.slice(0, 12)}</small>
                </span>
                <span>v{String(draft.revision_no)}</span>
                <StatusPill
                  tone={
                    draft.status === "published"
                      ? "good"
                      : draft.status === "rejected"
                        ? "warn"
                        : "neutral"
                  }
                >
                  {draft.status}
                </StatusPill>
                <span>
                  {new Date(draft.created_at).toLocaleDateString("fr-FR")}
                </span>
              </button>
            ))}
          </div>
          <div className="editorial-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">
                  {selected
                    ? `Révision ${String(selected.revision_no)}`
                    : "Nouveau contenu"}
                </p>
                <h2>{selected ? selected.status : "Brouillon"}</h2>
              </div>
              {selected ? <StatusPill>{selected.status}</StatusPill> : null}
            </div>
            {!selected ? (
              <label>
                Type de contenu
                <input
                  value={contentType}
                  onChange={(event) => {
                    setContentType(event.target.value);
                  }}
                />
              </label>
            ) : null}
            <label>
              Payload JSON
              <textarea
                rows={14}
                value={payloadText}
                onChange={(event) => {
                  setPayloadText(event.target.value);
                }}
              />
            </label>
            {error ? <ErrorRegion message={error} /> : null}
            <div className="editorial-actions">
              {!selected && canAuthor ? (
                <button
                  disabled={busy}
                  type="button"
                  onClick={() => void create()}
                >
                  Créer le brouillon
                </button>
              ) : null}
              {selected?.status === "draft" && canAuthor ? (
                <>
                  <button
                    className="secondary-button"
                    disabled={busy || version === undefined}
                    type="button"
                    onClick={() =>
                      void run(() =>
                        reviseContentDraft(
                          selected.content_revision_id,
                          {
                            payload: parsePayload(),
                            provenance_id: uuid7(),
                            rights_ref: "original:polyglot-author",
                          },
                          commandFetch(session, version),
                        ),
                      )
                    }
                  >
                    Créer une révision
                  </button>
                  <button
                    disabled={busy || version === undefined}
                    type="button"
                    onClick={() =>
                      void run(() =>
                        validateContentRevision(
                          selected.content_revision_id,
                          { validator_set_revision_id: uuid7() },
                          commandFetch(session, version),
                        ),
                      )
                    }
                  >
                    Valider
                  </button>
                </>
              ) : null}
              {selected?.status === "validated" && canReview ? (
                <>
                  <button
                    className="secondary-button"
                    disabled={busy || version === undefined}
                    type="button"
                    onClick={() =>
                      void run(() =>
                        approveContentRevision(
                          selected.content_revision_id,
                          {
                            decision: "rejected",
                            reason_code: "editorial_changes_required",
                          },
                          commandFetch(session, version),
                        ),
                      )
                    }
                  >
                    Rejeter
                  </button>
                  <button
                    disabled={busy || version === undefined}
                    type="button"
                    onClick={() =>
                      void run(() =>
                        approveContentRevision(
                          selected.content_revision_id,
                          {
                            decision: "approved",
                            reason_code: "editorial_review_passed",
                          },
                          commandFetch(session, version),
                        ),
                      )
                    }
                  >
                    Approuver
                  </button>
                </>
              ) : null}
              {selected?.status === "approved" && canAuthor ? (
                <button
                  disabled={busy || version === undefined}
                  type="button"
                  onClick={() =>
                    void run(() =>
                      publishContentRevision(
                        selected.content_revision_id,
                        {
                          channel_code: "stable",
                          compatibility_range: ">=2.0.0 <3.0.0",
                          publication_provenance_id: uuid7(),
                        },
                        commandFetch(session, version),
                      ),
                    )
                  }
                >
                  Publier
                </button>
              ) : null}
              {selected?.status === "published" && canAuthor ? (
                <button
                  className="danger-button"
                  disabled={busy || version === undefined}
                  type="button"
                  onClick={() =>
                    void run(() =>
                      retireContentRevision(
                        selected.content_id,
                        selected.content_revision_id,
                        commandFetch(session, version),
                      ),
                    )
                  }
                >
                  Retirer
                </button>
              ) : null}
            </div>
          </div>
        </section>
        {drafts.length === 0 && !canAuthor ? (
          <section className="empty-panel">
            <FileClock aria-hidden="true" />
            <h2>Aucun brouillon</h2>
            <p>
              Les brouillons créés à la main ou par génération apparaîtront ici.
            </p>
          </section>
        ) : null}
      </div>
    </AuthorGuard>
  );
}

function schemaFields(tool: ToolDefinitionResponse): string[] {
  const required = tool.input_schema.required;
  return Array.isArray(required)
    ? required.filter((item): item is string => typeof item === "string")
    : [];
}

export function AuthoringToolsPage() {
  const session = useSession();
  const query = useListAuthoringTools({
    fetch: queryFetch(),
    query: { retry: false },
  });
  const invoke = useInvokeAuthoringTool({ fetch: commandFetch(session) });
  const allowedTools = useMemo(() => {
    const tools = query.data?.status === 200 ? query.data.data : [];
    return tools.filter((tool) =>
      tool.roles.some((role) => session.roles.includes(role)),
    );
  }, [query.data, session.roles]);
  const [selectedName, setSelectedName] = useState("");
  const selected =
    allowedTools.find((tool) => tool.name === selectedName) ?? allowedTools[0];
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState("");

  if (query.isPending) return <LoadingRegion label="Chargement des outils" />;

  async function run() {
    if (!selected) return;
    setError("");
    setResult(null);
    const input: Record<string, JsonValueInput> = {};
    for (const field of schemaFields(selected)) {
      const raw = values[field] ?? "";
      try {
        input[field] = JSON.parse(raw) as JsonValueInput;
      } catch {
        input[field] = raw;
      }
    }
    const response = await invoke.mutateAsync({
      toolName: selected.name,
      data: {
        actor_role: session.roles.includes("author") ? "author" : "reviewer",
        input,
        invocation_id: uuid7(),
        tool_version: selected.version,
        trace: { correlation_id: uuid7(), policy_revisions: {} },
      },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    setResult(response.data);
  }

  return (
    <AuthorGuard>
      <div className="page-flow">
        <PageHeader
          eyebrow="Runner déterministe"
          title="Outils auteur"
          description="Chaque entrée est validée par un schéma fermé et chaque sortie reste traçable."
          action={
            <StatusPill>{allowedTools.length} outils autorisés</StatusPill>
          }
        />
        {query.data && query.data.status !== 200 ? (
          <ErrorRegion message="Le catalogue d'outils n'est pas disponible." />
        ) : null}
        <section className="tool-workbench">
          <nav aria-label="Outils disponibles" className="tool-list">
            {allowedTools.map((tool) => (
              <button
                aria-pressed={selected?.name === tool.name}
                key={tool.name}
                type="button"
                onClick={() => {
                  setSelectedName(tool.name);
                  setValues({});
                  setResult(null);
                }}
              >
                <Braces aria-hidden="true" size={18} />
                <span>
                  {tool.name}
                  <small>{tool.effect}</small>
                </span>
              </button>
            ))}
          </nav>
          <div className="tool-form">
            {selected ? (
              <>
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">Contrat {selected.version}</p>
                    <h2>{selected.name}</h2>
                  </div>
                  <StatusPill
                    tone={selected.effect === "none" ? "neutral" : "warn"}
                  >
                    {selected.effect}
                  </StatusPill>
                </div>
                <p className="quiet-copy">
                  Délai maximal : {Math.round(selected.timeout_ms / 1000)} s. La
                  sortie ne peut ni publier ni attribuer une maîtrise.
                </p>
                {schemaFields(selected).map((field) => (
                  <label key={field}>
                    {field}
                    <textarea
                      rows={
                        field.includes("context") || field.includes("refs")
                          ? 3
                          : 2
                      }
                      value={values[field] ?? ""}
                      onChange={(event) => {
                        setValues((current) => ({
                          ...current,
                          [field]: event.target.value,
                        }));
                      }}
                    />
                  </label>
                ))}
                {error ? <ErrorRegion message={error} /> : null}
                <button
                  disabled={invoke.isPending}
                  type="button"
                  onClick={() => void run()}
                >
                  <Play aria-hidden="true" size={18} /> Exécuter
                </button>
                {result ? (
                  <div className="tool-result">
                    <CheckCircle2 aria-hidden="true" />
                    <div>
                      <strong>Sortie validée</strong>
                      <pre>{JSON.stringify(result, null, 2)}</pre>
                    </div>
                  </div>
                ) : null}
              </>
            ) : (
              <p>Aucun outil autorisé pour ce rôle.</p>
            )}
          </div>
        </section>
      </div>
    </AuthorGuard>
  );
}
