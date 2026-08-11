import { ArrowRight, Clock3, RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useActiveProfile } from "../../app/profile-state";
import { useSession } from "../../app/session-context";
import { ErrorRegion, LoadingRegion, NoProfile, PageHeader, StatusPill } from "../../components/product-ui";
import type { SessionPlanResponse } from "../../generated/model";
import { useComposeDailySession, usePrepareSessionPlan, useStartSprintRun } from "../../generated/polyglot";
import { commandFetch, responseProblem, todayIso } from "../../lib/api";
import { uuid7 } from "../../lib/ids";
import { DailyVocabulary } from "./daily-vocabulary";

const budgets = [10, 20, 30, 45, 60] as const;

export function TodayPage() {
  const { activeProfile, isPending } = useActiveProfile();
  const session = useSession();
  const navigate = useNavigate();
  const [budget, setBudget] = useState(30);
  const [plan, setPlan] = useState<SessionPlanResponse | null>(null);
  const [error, setError] = useState("");
  const compose = useComposeDailySession({ fetch: commandFetch(session) });
  const prepare = usePrepareSessionPlan({ fetch: commandFetch(session, plan?.version) });
  const start = useStartSprintRun({ fetch: commandFetch(session) });

  if (isPending) return <LoadingRegion label="Préparation de votre journée" />;
  if (!activeProfile) return <NoProfile />;
  const profileId = activeProfile.profile_id;

  async function composePlan() {
    setError("");
    const response = await compose.mutateAsync({
      profileId,
      data: {
        budget_minutes: budget,
        pedagogical_day: todayIso(),
        plan_id: uuid7(),
        snapshot_id: uuid7(),
      },
    });
    const problem = responseProblem(response);
    if (problem) { setError(problem); return; }
    if (response.status === 201) setPlan(response.data);
  }

  async function begin() {
    if (!plan) return;
    setError("");
    const prepared = await prepare.mutateAsync({ planId: plan.plan_id, data: {} });
    const prepareProblem = responseProblem(prepared);
    if (prepareProblem) { setError(prepareProblem); return; }
    const runId = uuid7();
    const started = await start.mutateAsync({ planId: plan.plan_id, data: { run_id: runId } });
    const startProblem = responseProblem(started);
    if (startProblem) { setError(startProblem); return; }
    localStorage.setItem("polyglot.active-run", runId);
    void navigate(`/sprints/${runId}`);
  }

  return (
    <div className="page-flow">
      <PageHeader eyebrow={todayIso()} title="Aujourd'hui" description="Une séance construite autour de vos rappels, de votre module et des preuves encore fragiles." action={<StatusPill tone={plan ? "good" : "neutral"}>{plan ? "Prête" : "À composer"}</StatusPill>} />
      <DailyVocabulary profileId={profileId} session={session} />
      <section className="today-workbench">
        <div className="today-workbench__main">
          <div className="section-heading"><div><p className="eyebrow">Séance du jour</p><h2>{plan ? "Votre parcours est prêt" : "Combien de temps avez-vous ?"}</h2></div><Clock3 aria-hidden="true" /></div>
          <div aria-label="Durée de la séance" className="segmented-control">
            {budgets.map((minutes) => <button aria-pressed={budget === minutes} className="segment" key={minutes} type="button" onClick={() => { setBudget(minutes); }}>{minutes}<small>min</small></button>)}
          </div>
          {plan ? (
            <div className="plan-summary">
              <div className="plan-summary__number">{plan.blocks.length}</div>
              <div><strong>étapes coordonnées</strong><p>{Math.round(plan.total_p80_seconds / 60)} min au rythme prudent · {plan.novelty_points} points de nouveauté</p></div>
            </div>
          ) : (
            <p className="quiet-copy">La durée ajuste le nombre d'exercices, jamais la qualité de la correction ni la continuité J+1.</p>
          )}
          {error ? <ErrorRegion message={error} /> : null}
          {plan ? <button disabled={prepare.isPending || start.isPending} type="button" onClick={() => void begin()}>Commencer la séance <ArrowRight aria-hidden="true" size={18} /></button> : <button disabled={compose.isPending} type="button" onClick={() => void composePlan()}>{compose.isPending ? "Composition..." : "Composer ma séance"} <Sparkles aria-hidden="true" size={18} /></button>}
        </div>
        <aside className="today-workbench__aside">
          <p className="eyebrow">Pourquoi maintenant ?</p>
          <h3>Réactiver avant d'ajouter</h3>
          <p>Les mots à échéance et les structures hésitantes passent avant les nouveautés.</p>
          <dl className="compact-facts"><div><dt>Rappels</dt><dd>prioritaires</dd></div><div><dt>Grammaire</dt><dd>en contexte</dd></div><div><dt>Production</dt><dd>corrigée</dd></div></dl>
        </aside>
      </section>
      <section className="recommendation-band">
        <div><RefreshCw aria-hidden="true" size={20} /><span><strong>Une révision ciblée reste disponible</strong><small>Travaillez librement sans modifier l'ordre de votre module.</small></span></div>
        <Link to="/practice">S'entraîner <ArrowRight aria-hidden="true" size={17} /></Link>
      </section>
    </div>
  );
}
