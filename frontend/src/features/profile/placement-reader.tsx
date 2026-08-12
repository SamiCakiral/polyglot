import { Headphones, Play } from "lucide-react";

interface Item {
  item_instance_id: string;
  primary_skill_ref: string;
  payload: {
    prompt?: unknown;
    response_kind?: unknown;
    choices?: unknown;
    tts_text?: unknown;
  };
}

export function PlacementReader({
  item,
  value,
  onChange,
}: {
  item: Item;
  value: string;
  onChange: (value: string) => void;
}) {
  const prompt = typeof item.payload.prompt === "string" ? item.payload.prompt : "Répondez.";
  const choices = Array.isArray(item.payload.choices)
    ? item.payload.choices.filter((choice): choice is string => typeof choice === "string")
    : [];
  const ttsText = typeof item.payload.tts_text === "string" ? item.payload.tts_text : "";

  function playAudio() {
    if (!ttsText || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(ttsText);
    utterance.lang = /[ぁ-んァ-ン一-龯]/u.test(ttsText) ? "ja-JP" : "it-IT";
    window.speechSynthesis.speak(utterance);
  }

  return (
    <section className="placement-task" aria-labelledby="placement-prompt">
      <div className="placement-task__meta">
        <span>{item.primary_skill_ref.replaceAll("_", " ")}</span>
        {ttsText ? <Headphones aria-hidden="true" size={18} /> : null}
      </div>
      <h2 id="placement-prompt">{prompt}</h2>
      {ttsText ? (
        <button className="secondary-button" type="button" onClick={playAudio}>
          <Play aria-hidden="true" size={18} /> Écouter
        </button>
      ) : null}
      {choices.length ? (
        <fieldset className="placement-choices">
          <legend className="sr-only">Choisissez une réponse</legend>
          {choices.map((choice) => (
            <label className="choice-row" key={choice}>
              <input
                checked={value === choice}
                name={item.item_instance_id}
                type="radio"
                value={choice}
                onChange={() => {
                  onChange(choice);
                }}
              />
              <span>{choice}</span>
            </label>
          ))}
        </fieldset>
      ) : (
        <label className="answer-field">
          Votre réponse
          <textarea
            autoFocus
            rows={5}
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
            }}
          />
        </label>
      )}
    </section>
  );
}
