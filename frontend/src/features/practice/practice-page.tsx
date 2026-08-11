import { ArrowRight, Dumbbell, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useActiveProfile } from "../../app/profile-state";
import { useSession } from "../../app/session-context";
import { ErrorRegion, NoProfile, PageHeader } from "../../components/product-ui";
import { prepareSessionPlan, startSprintRun, useComposeFreePractice } from "../../generated/polyglot";
import { commandFetch, responseProblem, todayIso } from "../../lib/api";
import { uuid7 } from "../../lib/ids";

const focusOptions = [
  {
    id: "grammar",
    label: "Transformer des phrases",
    primitives: ["EX-RECALL-04", "EX-REPAIR-01", "EX-TRANSFORM-01"],
    target: "grammar:review",
  },
  {
    id: "writing",
    label: "Écrire dans une situation",
    primitives: ["EX-RECALL-04", "EX-COMP-03", "EX-PROD-01"],
    target: "communication:writing",
  },
  {
    id: "vocabulary",
    label: "Réactiver du vocabulaire",
    primitives: ["EX-EXPOSE-01", "EX-RECALL-04", "EX-DISC-04"],
    target: "lexicon:due",
  },
] as const;

export function PracticePage() {
  const { activeProfile } = useActiveProfile();
  const session = useSession();
  const navigate = useNavigate();
  const [focus, setFocus] = useState<(typeof focusOptions)[number]>(focusOptions[0]);
  const [budget, setBudget] = useState(20);
  const [challenge, setChallenge] = useState("matched");
  const [error, setError] = useState("");
  const compose = useComposeFreePractice({ fetch: commandFetch(session) });
  const activeRunId = localStorage.getItem("polyglot.active-run");

  if (!activeProfile) return <NoProfile />;
  const profileId = activeProfile.profile_id;

  async function launch() {
    setError("");
    const planId = uuid7();
    const response = await compose.mutateAsync({ profileId, data: { allow_novelty: false, budget_minutes: budget, challenge, modalities: focus.id === "writing" ? ["writing"] : ["reading", "writing"], pedagogical_day: todayIso(), plan_id: planId, primitive_ids: [...focus.primitives], snapshot_id: uuid7(), target_refs: [focus.target] } });
    const problem = responseProblem(response);
    if (problem) { setError(problem); return; }
    if (response.status !== 201) { setError("La séance n'a pas pu être composée."); return; }
    const prepared = await prepareSessionPlan(planId, {}, commandFetch(session, response.data.version));
    const prepareProblem = responseProblem(prepared);
    if (prepareProblem) { setError(prepareProblem); return; }
    const runId = uuid7();
    const started = await startSprintRun(planId, { run_id: runId }, commandFetch(session));
    const startProblem = responseProblem(started);
    if (startProblem) { setError(startProblem); return; }
    localStorage.setItem("polyglot.active-run", runId);
    void navigate(`/sprints/${runId}`);
  }

  return (
    <div className="page-flow">
      <PageHeader eyebrow="Hors curriculum" title="S'entraîner" description="Ciblez un besoin précis sans déplacer la séance quotidienne ni créer de faux crédit." action={<SlidersHorizontal aria-hidden="true" />} />
      <section className="practice-configurator">
        <div><p className="eyebrow">Cible</p><h2>Que voulez-vous travailler ?</h2><div className="choice-stack">{focusOptions.map((option) => <button aria-pressed={focus.id === option.id} className="practice-choice" key={option.id} type="button" onClick={() => { setFocus(option); }}><Dumbbell aria-hidden="true" size={20} /><span>{option.label}<small>{option.id === "grammar" ? "Boîte grammaticale et Gym" : option.id === "writing" ? "Production avec correction" : "Rappel actif et contexte"}</small></span></button>)}</div></div>
        <div className="practice-options"><label>Durée<select value={budget} onChange={(event) => { setBudget(Number(event.target.value)); }}><option value={10}>10 minutes</option><option value={20}>20 minutes</option><option value={30}>30 minutes</option><option value={45}>45 minutes</option></select></label><label>Difficulté<select value={challenge} onChange={(event) => { setChallenge(event.target.value); }}><option value="gentler">Guidée</option><option value="matched">Équilibrée</option><option value="stretch">Exigeante</option></select></label><p>Les nouveautés sont désactivées : cette séance travaille uniquement des cibles déjà rencontrées.</p>{error ? <ErrorRegion message={error} /> : null}{activeRunId ? <button type="button" onClick={() => { void navigate(`/sprints/${activeRunId}`); }}>Reprendre la séance en cours <ArrowRight aria-hidden="true" size={18} /></button> : <button disabled={compose.isPending} type="button" onClick={() => void launch()}>Lancer l'entraînement <ArrowRight aria-hidden="true" size={18} /></button>}</div>
      </section>
    </div>
  );
}
