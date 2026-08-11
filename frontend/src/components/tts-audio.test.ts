import { describe, expect, it } from "vitest";

import { selectAvailableVoice } from "./tts-voice";

describe("selectAvailableVoice", () => {
  it("selects an available voice for the active locale", () => {
    const voice = selectAvailableVoice(
      [
        { availability: "available", language_tags: ["it-IT"], voice_id: "Alice" },
        { availability: "available", language_tags: ["ja-JP"], voice_id: "Kyoko" },
      ],
      "ja-JP",
    );

    expect(voice?.voice_id).toBe("Kyoko");
  });

  it("does not silently use another language", () => {
    const voice = selectAvailableVoice(
      [{ availability: "available", language_tags: ["it-IT"], voice_id: "Alice" }],
      "ja-JP",
    );

    expect(voice).toBeNull();
  });
});
