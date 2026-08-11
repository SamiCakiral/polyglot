import { Volume2 } from "lucide-react";
import { useState } from "react";

import type { CurrentSessionResponse } from "../generated/model";
import { synthesizeSpeech } from "../generated/polyglot";
import { commandFetch, responseProblem } from "../lib/api";

type SpeechSource =
  | { text: string; assessmentRunId?: never; assessmentItemId?: never }
  | { text?: never; assessmentRunId: string; assessmentItemId: string };

type TtsAudioProps = SpeechSource & {
  session: CurrentSessionResponse;
  label?: string;
  maxPlays?: number | null;
};

export function TtsAudio({
  session,
  label = "Écouter",
  maxPlays = null,
  ...source
}: TtsAudioProps) {
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [plays, setPlays] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const exhausted = maxPlays !== null && plays >= maxPlays;

  async function play() {
    setBusy(true);
    setError("");
    const response = await synthesizeSpeech(
      {
        locale: "it-IT",
        parameters: {},
        voice_id: "Alice",
        ...(source.text !== undefined
          ? { text: source.text }
          : {
              assessment_run_id: source.assessmentRunId,
              assessment_item_id: source.assessmentItemId,
            }),
      },
      commandFetch(session),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      setBusy(false);
      return;
    }
    if (
      response.status !== 200 ||
      response.data.availability !== "available" ||
      !response.data.media?.read_url
    ) {
      setError(
        "La voix italienne est indisponible. Aucune écoute n'est comptabilisée.",
      );
      setBusy(false);
      return;
    }
    setAudioUrl(response.data.media.read_url);
    setPlays((value) => value + 1);
    setBusy(false);
  }

  return (
    <div className="tts-player">
      <button
        className="secondary-button audio-button"
        disabled={busy || exhausted}
        type="button"
        onClick={() => void play()}
      >
        <Volume2 aria-hidden="true" size={18} />
        {busy ? "Préparation..." : exhausted ? "Limite atteinte" : label}
      </button>
      {maxPlays !== null ? (
        <span aria-live="polite">
          {String(plays)} / {String(maxPlays)} écoute{maxPlays > 1 ? "s" : ""}
        </span>
      ) : null}
      {audioUrl ? (
        <audio key={audioUrl} autoPlay controls src={audioUrl} />
      ) : null}
      {error ? (
        <p className="form-warning" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
