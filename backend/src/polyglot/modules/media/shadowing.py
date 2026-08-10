from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ShadowingAvailability(StrEnum):
    AUDIO_AVAILABLE = "audio_available"
    ALTERNATIVE_AVAILABLE = "alternative_available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ShadowingPrompt:
    availability: ShadowingAvailability
    audio: bytes | None
    transcript: str | None
    evaluable: bool

    @classmethod
    def from_fixture(cls, *, audio: bytes | None, transcript: str | None) -> ShadowingPrompt:
        if audio is not None:
            return cls(ShadowingAvailability.AUDIO_AVAILABLE, audio, transcript, False)
        if transcript:
            return cls(ShadowingAvailability.ALTERNATIVE_AVAILABLE, None, transcript, False)
        return cls(ShadowingAvailability.UNAVAILABLE, None, None, False)
