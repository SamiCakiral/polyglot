import { ArrowRight, Pause } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useSession } from "../../app/session-context";
import { useActiveProfile } from "../../app/profile-state";
import { ErrorRegion, LoadingRegion, PageHeader, StatusPill } from "../../components/product-ui";
import { uuid7 } from "../../lib/ids";
import { PlacementReader } from "./placement-reader";
import { PlacementResult } from "./placement-result";
import { forgetPlacementRun, placementRunKey, rememberPlacementRun } from "./placement-state";

type EntryPath = "complete_beginner" | "already_started" | "advanced";
interface Estimate {
  skill_ref: string;
  status: string;
  lower_bound: number | null;
  probable_level: number | null;
  upper_bound: number | null;
  confidence: number;
  independent_evidence_count: number;
}
interface Item {
  item_instance_id: string;
  ordinal: number;
  primitive_ref: string;
  primary_skill_ref: string;
  payload: { prompt?: unknown; response_kind?: unknown; choices?: unknown; tts_text?: unknown };
  estimated_seconds: number;
}
interface Run {
  run_id: string;
  profile_id: string;
  status: "active" | "complete" | "partial" | "cancelled";
  version: number;
  elapsed_seconds: number;
  current_item: Item | null;
  estimates: Estimate[];
  stop_reason: string | null;
  provider_status: string | null;
}

async function readProblem(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string; title?: string };
    return body.detail ?? body.title ?? "La demande n'a pas pu aboutir.";
  } catch {
    return "La demande n'a pas pu aboutir.";
  }
}

export function AdaptivePlacementPanel({
  profileId,
  packRevisionId,
  entryPath,
  targetName,
}: {
  profileId: string;
  packRevisionId: string;
  entryPath: EntryPath;
  targetName: string;
}) {
  const session = useSession();
  const { refresh } = useActiveProfile();
  const navigate = useNavigate();
  const [run, setRun] = useState<Run | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const shownAt = useRef(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setError("");
      const stored = localStorage.getItem(placementRunKey(profileId));
      let response = stored
        ? await fetch(`/api/v1/placement-runs/${stored}`, { credentials: "include" })
        : null;
      if (!response?.ok) {
        response = await fetch(`/api/v1/language-profiles/${profileId}/placement-runs`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": uuid7(),
            "X-CSRF-Token": session.csrf_token,
          },
          body: JSON.stringify({ pack_revision_id: packRevisionId, entry_path: entryPath, seed: uuid7() }),
        });
      }
      if (!response.ok) throw new Error(await readProblem(response));
      const loaded = (await response.json()) as Run;
      if (!cancelled) {
        rememberPlacementRun(profileId, loaded.run_id);
        setRun(loaded);
        shownAt.current = Date.now();
      }
    }
    void load().catch((caught: unknown) => {
      if (!cancelled) setError(caught instanceof Error ? caught.message : "Le diagnostic est indisponible.");
    });
    return () => { cancelled = true; };
  }, [entryPath, packRevisionId, profileId, session.csrf_token]);

  async function submit() {
    if (!run?.current_item || !answer.trim()) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/placement-runs/${run.run_id}/responses`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": uuid7(),
          "If-Match": `"${String(run.version)}"`,
          "X-CSRF-Token": session.csrf_token,
        },
        body: JSON.stringify({
          item_instance_id: run.current_item.item_instance_id,
          answer: { value: answer },
          elapsed_seconds: Math.max(1, Math.round((Date.now() - shownAt.current) / 1000)),
        }),
      });
      if (!response.ok) throw new Error(await readProblem(response));
      setRun((await response.json()) as Run);
      setAnswer("");
      shownAt.current = Date.now();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "La réponse n'a pas été enregistrée.");
    } finally {
      setBusy(false);
    }
  }

  async function choose(choice: "accept" | "start_easier" | "challenge" | "start_now") {
    if (!run) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/v1/placement-runs/${run.run_id}:choose`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": uuid7(),
          "If-Match": `"${String(run.version)}"`,
          "X-CSRF-Token": session.csrf_token,
        },
        body: JSON.stringify({ choice }),
      });
      if (!response.ok) throw new Error(await readProblem(response));
      await refresh();
      forgetPlacementRun(profileId);
      void navigate("/practice");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Le choix n'a pas été enregistré.");
      setBusy(false);
    }
  }

  if (error && !run) return <ErrorRegion message={error} />;
  if (!run) return <LoadingRegion label="Préparation du placement adaptatif" />;
  if (run.status !== "active" || !run.current_item) {
    return <PlacementResult estimates={run.estimates} busy={busy} onChoose={(choice) => void choose(choice)} />;
  }

  return (
    <div className="page-flow page-flow--narrow placement-flow">
      <PageHeader
        eyebrow="Placement adaptatif"
        title={`Trouver votre point de départ en ${targetName.toLocaleLowerCase("fr")}`}
        description="Une tâche à la fois. La difficulté et la modalité changent selon vos réponses."
        action={<StatusPill>{String(Math.max(1, Math.round(run.elapsed_seconds / 60)))} min</StatusPill>}
      />
      <div className="placement-progress" aria-label="Progression qualitative">
        <span
          style={{
            width: `${String(Math.min(100, Math.max(8, (run.elapsed_seconds / 720) * 100)))}%`,
          }}
        />
      </div>
      <PlacementReader item={run.current_item} value={answer} onChange={setAnswer} />
      {run.provider_status === "unavailable" ? (
        <ErrorRegion message="L'évaluation locale est temporairement indisponible. Cette réponse n'a pas été comptée contre vous." />
      ) : null}
      {error ? <ErrorRegion message={error} /> : null}
      <div className="placement-footer">
        <button className="text-button" type="button" onClick={() => void navigate("/practice")}>
          <Pause aria-hidden="true" size={18} /> Reprendre plus tard
        </button>
        <button disabled={busy || !answer.trim()} type="button" onClick={() => void submit()}>
          {busy ? "Analyse..." : "Valider et continuer"} <ArrowRight aria-hidden="true" size={18} />
        </button>
      </div>
    </div>
  );
}
