interface Estimate {
  skill_ref: string;
  status: string;
  probable_level: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  confidence: number;
  independent_evidence_count: number;
}

const labels: Record<string, string> = {
  script: "Écriture et sons",
  reading: "Compréhension écrite",
  listening: "Compréhension orale",
  writing: "Expression écrite",
  speaking: "Expression orale",
  vocabulary: "Vocabulaire",
  grammar_functions: "Boîte grammaticale",
  interaction_repair: "Réparer un échange",
  pragmatics_register: "Registre et situation",
};

export function PlacementResult({
  estimates,
  busy,
  onChoose,
}: {
  estimates: Estimate[];
  busy: boolean;
  onChoose: (choice: "accept" | "start_easier" | "challenge" | "start_now") => void;
}) {
  const complete = [
    ...estimates,
    {
      skill_ref: "speaking",
      status: "not_observed",
      probable_level: null,
      lower_bound: null,
      upper_bound: null,
      confidence: 0,
      independent_evidence_count: 0,
    },
  ];
  return (
    <section className="placement-result">
      <header>
        <p className="eyebrow">Point de départ proposé</p>
        <h1>Votre profil, compétence par compétence</h1>
        <p>Ce profil reste provisoire et sera affiné pendant vos trois premières séances.</p>
      </header>
      <div className="placement-skill-grid">
        {complete.map((estimate) => (
          <article className="placement-skill" key={estimate.skill_ref}>
            <h2>{labels[estimate.skill_ref] ?? estimate.skill_ref}</h2>
            {estimate.status === "not_observed" || estimate.independent_evidence_count === 0 ? (
              <strong>Non observé</strong>
            ) : (
              <strong>Niveau interne {estimate.probable_level}/8</strong>
            )}
            <p>
              {estimate.confidence >= 0.75
                ? "Estimation bien étayée"
                : estimate.confidence > 0
                  ? "Estimation à confirmer"
                  : "Aucune preuve disponible"}
            </p>
          </article>
        ))}
      </div>
      <div className="placement-actions">
        <button disabled={busy} type="button" onClick={() => { onChoose("accept"); }}>
          Accepter ce départ
        </button>
        <button className="secondary-button" disabled={busy} type="button" onClick={() => { onChoose("start_easier"); }}>
          Commencer plus doucement
        </button>
        <button className="secondary-button" disabled={busy} type="button" onClick={() => { onChoose("challenge"); }}>
          Me proposer un défi
        </button>
        <button className="text-button" disabled={busy} type="button" onClick={() => { onChoose("start_now"); }}>
          M'entraîner maintenant
        </button>
      </div>
    </section>
  );
}
