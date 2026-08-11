import {
  ArrowLeft,
  BookMarked,
  FolderOpen,
  ListPlus,
  Plus,
  Search,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
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
import {
  useCreateVocabularyList,
  useCreatePracticeStack,
  useFreezeVocabularyList,
  useGetLexicalSense,
  useGetVocabularyList,
  useGetWordBankOverview,
  useListVocabularyLists,
  useRecordLexicalEncounter,
  useResolveMention,
} from "../../generated/polyglot";
import { commandFetch, queryFetch, responseProblem } from "../../lib/api";
import { uuid7 } from "../../lib/ids";

const analysisLabels: Record<string, string> = {
  resolved: "Identifié",
  unresolved: "À clarifier",
  unobserved: "Non rencontré",
};

const reasonLabels: Record<string, string> = {
  encountered: "Rencontré dans une activité",
  absence_of_evidence: "Pas encore rencontré",
};

const listStatusLabels: Record<string, string> = {
  active: "Active",
  archived: "Archivée",
};

const knowledgeLabels: Record<string, string> = {
  unencountered: "Non rencontré",
  encountered: "Rencontré",
  recognized: "Reconnu",
  recalled: "Rappelé",
  guided_reuse: "Réutilisé avec aide",
  autonomous_reuse: "Réutilisé seul",
};

function wordCountLabel(count: number): string {
  return `${String(count)} mot${count > 1 ? "s" : ""}`;
}

interface VocabularyListSummary {
  list_id: string;
  member_count: number;
  name: string;
  version: number;
}

function vocabularyLists(data: unknown): VocabularyListSummary[] {
  if (
    !data ||
    typeof data !== "object" ||
    !("items" in data) ||
    !Array.isArray(data.items)
  )
    return [];
  return data.items.filter(
    (item): item is VocabularyListSummary =>
      Boolean(item) &&
      typeof item === "object" &&
      "list_id" in item &&
      "member_count" in item &&
      "name" in item,
  );
}

export function VocabularyPage() {
  const { activePack, activeProfile } = useActiveProfile();
  const session = useSession();
  const navigate = useNavigate();
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const [creatingStack, setCreatingStack] = useState(false);
  const [addingWord, setAddingWord] = useState(false);
  const [manualSurface, setManualSurface] = useState("");
  const [name, setName] = useState("");
  const [stackName, setStackName] = useState("");
  const [error, setError] = useState("");
  const profileId = activeProfile?.profile_id ?? "";
  const query = useGetWordBankOverview(
    profileId,
    { limit: 100 },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activeProfile), retry: false },
    },
  );
  const listsQuery = useListVocabularyLists(
    { profile_id: profileId, limit: 100 },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activeProfile), retry: false },
    },
  );
  const createList = useCreateVocabularyList({ fetch: commandFetch(session) });
  const createStack = useCreatePracticeStack({ fetch: commandFetch(session) });
  const recordEncounter = useRecordLexicalEncounter({
    fetch: commandFetch(session),
  });
  const resolveMention = useResolveMention({ fetch: commandFetch(session) });
  const overview = query.data?.status === 200 ? query.data.data : null;
  const unresolvedMentions = overview?.unresolved_mentions ?? [];
  const lists =
    listsQuery.data?.status === 200
      ? vocabularyLists(listsQuery.data.data)
      : [];
  const items = useMemo(
    () =>
      overview?.items.filter((item) =>
        item.label
          .toLocaleLowerCase(activePack?.target_language_tag)
          .includes(filter.toLocaleLowerCase(activePack?.target_language_tag)),
      ) ?? [],
    [activePack?.target_language_tag, filter, overview],
  );
  if (!activeProfile) return <NoProfile />;
  if (query.isPending || listsQuery.isPending)
    return <LoadingRegion label="Ouverture de votre banque de mots" />;
  const profile = activeProfile;

  function toggle(senseId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(senseId)) next.delete(senseId);
      else next.add(senseId);
      return next;
    });
  }

  async function create() {
    if (!name.trim()) return;
    setError("");
    const response = await createList.mutateAsync({
      profileId,
      data: {
        created_at: new Date().toISOString(),
        list_type: "manual",
        member_sense_ids: [...selected],
        name: name.trim(),
        ordered: true,
        purpose: "Liste personnelle de révision",
        tags: ["personnelle"],
        variety_id: profile.target_variety_id,
      },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    setName("");
    setSelected(new Set());
    setCreating(false);
    await listsQuery.refetch();
  }

  async function addManualWord() {
    const surface = manualSurface.trim();
    if (!surface) return;
    setError("");
    const now = new Date().toISOString();
    const response = await recordEncounter.mutateAsync({
      profileId,
      data: {
        data: {
          analysis_revision_ref: "manual-v1",
          context_fingerprint:
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
          context_retention: "minimal",
          correction_confidence: 0,
          correction_ref: "none",
          encounter_id: uuid7(),
          exact_surface: surface,
          help_state: "none",
          lexical_role: "learner_added",
          mention_id: uuid7(),
          modality: "reading",
          occurred_at: now,
          operation: "seen",
          result_state: "not_evaluable",
          source_ref: "user_word_bank",
          source_revision_ref: "manual-v1",
          source_type: "manual",
        },
      },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    setManualSurface("");
    setAddingWord(false);
    await query.refetch();
  }

  async function createTrainingStack() {
    if (!stackName.trim() || !activePack) return;
    const members = (overview?.items ?? [])
      .filter(
        (item) =>
          selected.has(item.sense_id) &&
          item.sense_revision_id &&
          item.definition,
      )
      .map((item) => ({
        definition: item.definition ?? "",
        label: item.label,
        sense_id: item.sense_id,
        sense_revision_id: item.sense_revision_id ?? "",
        source_kind: "word_bank_selection",
        source_ref: `word_bank:${item.sense_id}`,
      }));
    if (!members.length) {
      setError("Sélectionnez au moins un sens identifié.");
      return;
    }
    const response = await createStack.mutateAsync({
      profileId,
      data: {
        created_at: new Date().toISOString(),
        language_pack_revision_id: activePack.pack_revision_id,
        members,
        name: stackName.trim(),
        source_refs: ["word_bank:selection"],
        stack_kind: "selection",
      },
    });
    const problem = responseProblem(response);
    if (problem || response.status !== 201) {
      setError(problem || "La pile n'a pas pu être créée.");
      return;
    }
    setSelected(new Set());
    setStackName("");
    setCreatingStack(false);
    void navigate("/practice");
  }

  async function resolveManualMention(
    mentionId: string,
    candidateId: string,
  ) {
    setError("");
    const response = await resolveMention.mutateAsync({
      mentionId,
      data: {
        data: {
          candidate_id: candidateId,
          resolution_id: uuid7(),
        },
      },
    });
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      return;
    }
    await query.refetch();
  }

  return (
    <div className="page-flow">
      <PageHeader
        eyebrow="Mémoire personnelle"
        title="Vocabulaire"
        description="Tous les mots rencontrés, leurs contextes et leur état de travail dans un seul inventaire."
        action={
          <div className="button-row">
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setAddingWord((value) => !value);
              }}
            >
              <Plus aria-hidden="true" size={18} /> Ajouter un mot
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setCreating((value) => !value);
              }}
            >
              <ListPlus aria-hidden="true" size={18} /> Nouvelle liste
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                setCreatingStack((value) => !value);
              }}
            >
              <FolderOpen aria-hidden="true" size={18} /> Nouvelle pile
            </button>
          </div>
        }
      />
      {query.data && query.data.status !== 200 ? (
        <ErrorRegion message="Votre banque de mots n'est pas disponible." />
      ) : null}
      <section className="vocabulary-stats">
        <div>
          <strong>{overview?.encountered_sense_count ?? 0}</strong>
          <span>sens rencontrés</span>
        </div>
        <div>
          <strong>{overview?.unresolved_mention_count ?? 0}</strong>
          <span>mentions à clarifier</span>
        </div>
        <div>
          <strong>{overview?.reference_coverage_count ?? "—"}</strong>
          <span>sens de référence vus</span>
        </div>
      </section>
      {addingWord ? (
        <section className="list-composer">
          <div>
            <p className="eyebrow">Ajout manuel</p>
            <h2>Ajouter un mot rencontré ailleurs</h2>
            <p>
              Le sens restera à clarifier tant qu'il n'aura pas été identifié.
            </p>
          </div>
          <label>
            Mot ou expression en langue cible
            <input
              autoFocus
              lang={activePack?.target_language_tag}
              maxLength={200}
              value={manualSurface}
              onChange={(event) => {
                setManualSurface(event.target.value);
              }}
            />
          </label>
          {error ? <ErrorRegion message={error} /> : null}
          <div>
            <button
              className="icon-button secondary-button"
              aria-label="Annuler l'ajout"
              type="button"
              onClick={() => {
                setAddingWord(false);
              }}
            >
              <X aria-hidden="true" />
            </button>
            <button
              disabled={!manualSurface.trim() || recordEncounter.isPending}
              type="button"
              onClick={() => void addManualWord()}
            >
              Ajouter à ma banque
            </button>
          </div>
        </section>
      ) : null}
      {creating ? (
        <section className="list-composer">
          <div>
            <p className="eyebrow">Liste manuelle</p>
            <h2>Créer une liste à partir de la Word Bank</h2>
            <p>
              {selected.size} mot{selected.size > 1 ? "s" : ""} sélectionné
              {selected.size > 1 ? "s" : ""}
            </p>
          </div>
          <label>
            Nom de la liste
            <input
              autoFocus
              maxLength={200}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </label>
          {error ? <ErrorRegion message={error} /> : null}
          <div>
            <button
              className="icon-button secondary-button"
              aria-label="Annuler"
              type="button"
              onClick={() => {
                setCreating(false);
              }}
            >
              <X aria-hidden="true" />
            </button>
            <button
              disabled={!name.trim() || createList.isPending}
              type="button"
              onClick={() => void create()}
            >
              Créer avec {selected.size} mot{selected.size > 1 ? "s" : ""}
            </button>
          </div>
        </section>
      ) : null}
      {creatingStack ? (
        <section className="list-composer">
          <div>
            <p className="eyebrow">Pile d'entraînement</p>
            <h2>Figer une sélection de mots</h2>
            <p>{selected.size} sens sélectionnés dans votre Word Bank</p>
          </div>
          <label>
            Nom de la pile
            <input
              autoFocus
              maxLength={200}
              value={stackName}
              onChange={(event) => {
                setStackName(event.target.value);
              }}
            />
          </label>
          {error ? <ErrorRegion message={error} /> : null}
          <div>
            <button
              className="icon-button secondary-button"
              aria-label="Annuler"
              type="button"
              onClick={() => {
                setCreatingStack(false);
              }}
            >
              <X aria-hidden="true" />
            </button>
            <button
              disabled={
                !stackName.trim() || !selected.size || createStack.isPending
              }
              type="button"
              onClick={() => void createTrainingStack()}
            >
              Créer la pile
            </button>
          </div>
        </section>
      ) : null}
      {lists.length ? (
        <section className="vocabulary-lists">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Collections</p>
              <h2>Mes listes</h2>
            </div>
            <StatusPill>{lists.length}</StatusPill>
          </div>
          <div>
            {lists.map((list) => (
              <Link key={list.list_id} to={`/vocabulary/lists/${list.list_id}`}>
                <FolderOpen aria-hidden="true" size={20} />
                <span>
                  <strong>{list.name}</strong>
                  <small>
                    {wordCountLabel(list.member_count)} · version {list.version}
                  </small>
                </span>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
      {unresolvedMentions.length > 0 ? (
        <section className="vocabulary-lists">
          <div className="section-heading">
            <div>
              <p className="eyebrow">À identifier</p>
              <h2>Mentions à clarifier</h2>
            </div>
            <StatusPill tone="warn">{unresolvedMentions.length}</StatusPill>
          </div>
          <div>
            {unresolvedMentions.map((mention) => (
              <div className="unresolved-mention" key={mention.mention_id}>
                <BookMarked aria-hidden="true" size={20} />
                <span>
                  <strong lang={activePack?.target_language_tag}>
                    {mention.exact_surface}
                  </strong>
                  <small>Ajouté manuellement · sens non identifié</small>
                </span>
                {(mention.candidates ?? []).length ? (
                  <div className="mention-candidates">
                    {(mention.candidates ?? []).map((candidate) => (
                      <button
                        className="secondary-button"
                        disabled={resolveMention.isPending}
                        key={candidate.candidate_id}
                        type="button"
                        onClick={() =>
                          void resolveManualMention(
                            mention.mention_id,
                            candidate.candidate_id,
                          )
                        }
                      >
                        Confirmer {candidate.label} : {candidate.definition}
                      </button>
                    ))}
                  </div>
                ) : (
                  <small>Aucun sens du catalogue ne correspond exactement.</small>
                )}
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <div className="table-toolbar">
        <label className="search-field">
          <Search aria-hidden="true" size={18} />
          <span className="sr-only">Rechercher un mot</span>
          <input
            placeholder="Rechercher dans vos mots"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
            }}
          />
        </label>
        <span>{items.length} résultats</span>
      </div>
      <div className="data-table" role="table" aria-label="Mots rencontrés">
        <div className="data-table__head" role="row">
          <span role="columnheader">Mot</span>
          <span role="columnheader">Rencontres</span>
          <span role="columnheader">État</span>
          <span role="columnheader">Pourquoi</span>
        </div>
        {items.map((item) => (
          <div className="data-table__row" role="row" key={item.sense_id}>
            {creating || creatingStack ? (
              <label className="word-selection">
                <input
                  aria-label={`Sélectionner ${item.label}`}
                  checked={selected.has(item.sense_id)}
                  type="checkbox"
                  onChange={() => {
                    toggle(item.sense_id);
                  }}
                />
              </label>
            ) : null}
            <span className="word-label" role="cell">
              <Link
                lang={activePack?.target_language_tag}
                to={`/vocabulary/senses/${item.sense_id}`}
              >
                {item.label}
              </Link>
              <small>{item.definition}</small>
            </span>
            <span role="cell">{item.encounter_count}</span>
            <span role="cell">
              <StatusPill tone={item.projection?.debt ? "warn" : "neutral"}>
                {knowledgeLabels[item.projection?.knowledge.stage ?? ""] ??
                  analysisLabels[item.analysis_state] ??
                  item.analysis_state}
              </StatusPill>
            </span>
            <span role="cell">
              {reasonLabels[item.reasons[0] ?? ""] ??
                item.reasons[0] ??
                "Rencontré dans une activité"}
            </span>
          </div>
        ))}
      </div>
      {items.length === 0 ? (
        <section className="empty-panel">
          <BookMarked aria-hidden="true" />
          <h2>
            {filter
              ? "Aucun mot correspondant"
              : "Votre banque est encore vide"}
          </h2>
          <p>
            Les mots apparaîtront automatiquement dès votre première séance.
          </p>
        </section>
      ) : null}
    </div>
  );
}

export function VocabularyListDetailPage() {
  const { listId = "" } = useParams();
  const { activePack, activeProfile } = useActiveProfile();
  const session = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const profileId = activeProfile?.profile_id ?? "";
  const listQuery = useGetVocabularyList(listId, {
    fetch: queryFetch(),
    query: { retry: false },
  });
  const bankQuery = useGetWordBankOverview(
    activeProfile?.profile_id ?? "",
    { limit: 100 },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activeProfile), retry: false },
    },
  );
  const listVersion =
    listQuery.data?.status === 200 ? listQuery.data.data.version : undefined;
  const freezeList = useFreezeVocabularyList({
    fetch: commandFetch(session, listVersion),
  });
  const createStack = useCreatePracticeStack({ fetch: commandFetch(session) });
  if (!activeProfile) return <NoProfile />;
  if (listQuery.isPending || bankQuery.isPending)
    return <LoadingRegion label="Ouverture de la liste" />;
  if (listQuery.data?.status !== 200)
    return <ErrorRegion message="Cette liste n'est pas disponible." />;
  const list = listQuery.data.data;
  const bank = bankQuery.data?.status === 200 ? bankQuery.data.data.items : [];
  const words = list.member_sense_ids
    .map((senseId) => bank.find((item) => item.sense_id === senseId))
    .filter((item) => item !== undefined);

  async function trainList() {
    setError("");
    const at = new Date().toISOString();
    const snapshot = await freezeList.mutateAsync({
      listId,
      data: { at },
    });
    const snapshotProblem = responseProblem(snapshot);
    if (snapshotProblem || snapshot.status !== 200) {
      setError(snapshotProblem || "La liste n'a pas pu être figée.");
      return;
    }
    const stack = await createStack.mutateAsync({
      profileId,
      data: {
        created_at: at,
        name: list.name,
        source_list_snapshot_id: snapshot.data.snapshot_id,
        source_refs: [`vocabulary_list:${list.list_id}`],
        stack_kind: "list_snapshot",
      },
    });
    const stackProblem = responseProblem(stack);
    if (stackProblem || stack.status !== 201) {
      setError(stackProblem || "La pile n'a pas pu être créée.");
      return;
    }
    void navigate("/practice");
  }
  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow="Liste personnelle"
        title={list.name}
        description={list.purpose}
        action={
          <StatusPill>
            {listStatusLabels[list.status] ?? list.status}
          </StatusPill>
        }
      />
      <section className="vocabulary-list-detail">
        <p>
          {wordCountLabel(list.member_sense_ids.length)} · révision{" "}
          {list.revision_no}
        </p>
        {words.map((word) => (
          <div key={word.sense_id}>
            <strong lang={activePack?.target_language_tag}>{word.label}</strong>
            <span>{word.definition ?? "Définition indisponible"}</span>
          </div>
        ))}
        {words.length === 0 ? (
          <p>Cette liste ne contient encore aucun mot de votre Word Bank.</p>
        ) : null}
      </section>
      {error ? <ErrorRegion message={error} /> : null}
      <button
        disabled={
          !words.length || freezeList.isPending || createStack.isPending
        }
        type="button"
        onClick={() => void trainList()}
      >
        <FolderOpen aria-hidden="true" size={18} /> Entraîner cette liste
      </button>
      <Link className="text-link" to="/vocabulary">
        Retour au vocabulaire
      </Link>
    </div>
  );
}

export function VocabularySenseDetailPage() {
  const { senseId = "" } = useParams();
  const { activeProfile } = useActiveProfile();
  const senseQuery = useGetLexicalSense(
    senseId,
    {
      depth: 1,
      edge_types: ["synonym", "antonym", "hypernym", "related"],
      max_nodes: 40,
      profile_id: activeProfile?.profile_id ?? "",
    },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activeProfile && senseId), retry: false },
    },
  );
  const bankQuery = useGetWordBankOverview(
    activeProfile?.profile_id ?? "",
    { limit: 100 },
    {
      fetch: queryFetch(),
      query: { enabled: Boolean(activeProfile), retry: false },
    },
  );
  if (!activeProfile) return <NoProfile />;
  if (senseQuery.isPending || bankQuery.isPending)
    return <LoadingRegion label="Ouverture du mot" />;
  const sense = senseQuery.data?.status === 200 ? senseQuery.data.data : null;
  const personal =
    bankQuery.data?.status === 200
      ? bankQuery.data.data.items.find((item) => item.sense_id === senseId)
      : null;

  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow="Sens lexical"
        title={personal?.label ?? sense?.label ?? "Détail du mot"}
        description={
          sense?.definition ??
          personal?.definition ??
          "Ce sens lexical n'est pas disponible dans le catalogue actif."
        }
        action={
          personal ? (
            <StatusPill>
              {analysisLabels[personal.analysis_state] ??
                personal.analysis_state}
            </StatusPill>
          ) : null
        }
      />
      {senseQuery.data && senseQuery.data.status !== 200 ? (
        <ErrorRegion message="Le détail canonique de ce mot n'est pas disponible." />
      ) : null}
      {personal ? (
        <section className="sense-evidence">
          <div>
            <strong>{personal.encounter_count}</strong>
            <span>rencontres enregistrées</span>
          </div>
          <div>
            <strong>{personal.learning_preference}</strong>
            <span>mode d'apprentissage</span>
          </div>
          <div>
            <strong>
              {personal.last_encountered_at
                ? new Date(personal.last_encountered_at).toLocaleDateString(
                    "fr-FR",
                  )
                : "Inconnue"}
            </strong>
            <span>dernière rencontre</span>
          </div>
        </section>
      ) : (
        <section className="empty-panel">
          <h2>Pas encore dans votre Word Bank</h2>
          <p>Ce sens canonique n'a pas encore été rencontré dans une séance.</p>
        </section>
      )}
      <Link className="text-link" to="/vocabulary">
        <ArrowLeft aria-hidden="true" size={17} /> Retour au vocabulaire
      </Link>
    </div>
  );
}
