import { Volume2 } from "lucide-react";
import { useState } from "react";

import type { CurrentSessionResponse } from "../generated/model";
import { getTtsCapabilities, synthesizeSpeech } from "../generated/polyglot";
import { commandFetch, queryFetch, responseProblem } from "../lib/api";
import { selectAvailableVoice } from "./tts-voice";

type SpeechSource =
  | { text: string; assessmentRunId?: never; assessmentItemId?: never }
  | { text?: never; assessmentRunId: string; assessmentItemId: string };

type TtsAudioProps = SpeechSource & {
  session: CurrentSessionResponse;
  locale: string;
  label?: string;
  maxPlays?: number | null;
};

export function TtsAudio({
  session,
  locale,
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
    const capabilities = await getTtsCapabilities({ language: locale }, queryFetch());
    const capabilitiesProblem = responseProblem(capabilities);
    if (capabilitiesProblem || capabilities.status !== 200) {
      setError(capabilitiesProblem || "La synthèse vocale est indisponible.");
      setBusy(false);
      return;
    }
    const voice = selectAvailableVoice(capabilities.data.voices, locale);
    if (!voice) {
      setError(`Aucune voix ${locale} n'est disponible. Aucune écoute n'est comptabilisée.`);
      setBusy(false);
      return;
    }
    const response = await synthesizeSpeech(
      {
        locale,
        parameters: {},
        voice_id: voice.voice_id,
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
      setError("La synthèse vocale est indisponible. Aucune écoute n'est comptabilisée.");
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
