interface VoiceCandidate {
  availability: string;
  language_tags: string[];
  voice_id: string;
}

export function selectAvailableVoice(
  voices: readonly VoiceCandidate[],
  locale: string,
): VoiceCandidate | null {
  return (
    voices.find(
      (voice) =>
        voice.availability === "available" && voice.language_tags.includes(locale),
    ) ?? null
  );
}
