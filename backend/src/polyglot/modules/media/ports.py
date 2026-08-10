from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class ObjectStoragePort(Protocol):
    def write_private(self, object_key: str, content: bytes) -> None: ...

    def read_private(self, object_key: str) -> bytes | None: ...

    def delete_private(self, object_key: str) -> None: ...

    def list_private(self, prefix: str) -> tuple[str, ...]: ...


@dataclass(slots=True)
class FakeObjectStorage:
    _objects: dict[str, bytes] = field(default_factory=dict)

    def write_private(self, object_key: str, content: bytes) -> None:
        if not object_key.startswith("media/"):
            raise ValueError("private media keys must use the media namespace")
        self._objects[object_key] = bytes(content)

    def read_private(self, object_key: str) -> bytes | None:
        content = self._objects.get(object_key)
        return None if content is None else bytes(content)

    def delete_private(self, object_key: str) -> None:
        self._objects.pop(object_key, None)

    def list_private(self, prefix: str) -> tuple[str, ...]:
        return tuple(sorted(key for key in self._objects if key.startswith(prefix)))


class TtsAvailability(StrEnum):
    AVAILABLE = "available"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    RETIRED = "retired"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class TtsVoice:
    voice_id: str
    locale: str
    availability: TtsAvailability
    provider_version: str


@dataclass(frozen=True, slots=True)
class TtsRequest:
    text: str
    locale: str
    voice_id: str
    parameters: Mapping[str, str]

    def cache_key(self, provider_version: str) -> str:
        canonical = json.dumps(
            {
                "locale": self.locale,
                "parameters": dict(sorted(self.parameters.items())),
                "provider_version": provider_version,
                "text": self.text,
                "voice_id": self.voice_id,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TtsSynthesis:
    voice_id: str
    availability: TtsAvailability
    cache_key: str | None
    audio: bytes | None


class TtsPort(Protocol):
    def list_voices(self) -> tuple[TtsVoice, ...]: ...

    def synthesize(self, request: TtsRequest) -> TtsSynthesis: ...


def _voice_result(voices: tuple[TtsVoice, ...], request: TtsRequest) -> TtsVoice | TtsSynthesis:
    voice = next(
        (candidate for candidate in voices if candidate.voice_id == request.voice_id),
        None,
    )
    if voice is None:
        return TtsSynthesis(request.voice_id, TtsAvailability.RETIRED, None, None)
    if voice.locale != request.locale:
        return TtsSynthesis(request.voice_id, TtsAvailability.UNSUPPORTED, None, None)
    if voice.availability is not TtsAvailability.AVAILABLE:
        return TtsSynthesis(request.voice_id, voice.availability, None, None)
    return voice


@dataclass(slots=True)
class DeterministicTtsPort:
    voices: tuple[TtsVoice, ...] = ()
    provider_available: bool = True
    _cache: dict[str, bytes] = field(default_factory=dict)

    @classmethod
    def unavailable(cls) -> DeterministicTtsPort:
        return cls(provider_available=False)

    def list_voices(self) -> tuple[TtsVoice, ...]:
        return self.voices

    def withdraw_voice(self, voice_id: str) -> DeterministicTtsPort:
        return DeterministicTtsPort(
            voices=tuple(
                TtsVoice(
                    voice_id=voice.voice_id,
                    locale=voice.locale,
                    availability=(
                        TtsAvailability.RETIRED
                        if voice.voice_id == voice_id
                        else voice.availability
                    ),
                    provider_version=voice.provider_version,
                )
                for voice in self.voices
            ),
            provider_available=self.provider_available,
            _cache=dict(self._cache),
        )

    def synthesize(self, request: TtsRequest) -> TtsSynthesis:
        if not self.provider_available:
            return TtsSynthesis(
                request.voice_id,
                TtsAvailability.TEMPORARILY_UNAVAILABLE,
                None,
                None,
            )
        result = _voice_result(self.voices, request)
        if isinstance(result, TtsSynthesis):
            return result
        cache_key = request.cache_key(result.provider_version)
        audio = self._cache.setdefault(cache_key, b"FX-TTS:" + cache_key.encode("ascii"))
        return TtsSynthesis(request.voice_id, TtsAvailability.AVAILABLE, cache_key, audio)


class CommandRunner(Protocol):
    def run(self, command: tuple[str, ...]) -> None: ...


class SubprocessCommandRunner:
    def run(self, command: tuple[str, ...]) -> None:
        subprocess.run(command, check=True, capture_output=True)


@dataclass(slots=True)
class MacOSTtsPort:
    voices: tuple[TtsVoice, ...]
    cache_dir: Path
    runner: CommandRunner | None = None

    def list_voices(self) -> tuple[TtsVoice, ...]:
        return self.voices

    def synthesize(self, request: TtsRequest) -> TtsSynthesis:
        result = _voice_result(self.voices, request)
        if isinstance(result, TtsSynthesis):
            return result
        if self.runner is None and sys.platform != "darwin":
            return TtsSynthesis(
                request.voice_id,
                TtsAvailability.TEMPORARILY_UNAVAILABLE,
                None,
                None,
            )
        cache_key = request.cache_key(result.provider_version)
        output_path = self.cache_dir / f"{cache_key}.mp3"
        if output_path.is_file():
            return TtsSynthesis(
                request.voice_id,
                TtsAvailability.AVAILABLE,
                cache_key,
                output_path.read_bytes(),
            )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        raw_path = self.cache_dir / f"{cache_key}.aiff"
        runner = self.runner or SubprocessCommandRunner()
        try:
            runner.run(("say", "-v", result.voice_id, "-o", str(raw_path), request.text))
            runner.run(("ffmpeg", "-nostdin", "-y", "-i", str(raw_path), str(output_path)))
            audio = output_path.read_bytes()
        except (OSError, subprocess.CalledProcessError):
            return TtsSynthesis(
                request.voice_id,
                TtsAvailability.TEMPORARILY_UNAVAILABLE,
                None,
                None,
            )
        finally:
            raw_path.unlink(missing_ok=True)
        return TtsSynthesis(request.voice_id, TtsAvailability.AVAILABLE, cache_key, audio)


@dataclass(frozen=True, slots=True)
class SttTranscript:
    available: bool
    text: str | None


class SttPort(Protocol):
    def transcribe(self, audio: bytes, *, locale: str) -> SttTranscript: ...


@dataclass(frozen=True, slots=True)
class DeterministicSttPort:
    transcripts: Mapping[str, str]

    @classmethod
    def from_transcripts(cls, transcripts: Mapping[bytes, str]) -> DeterministicSttPort:
        return cls(
            {
                hashlib.sha256(audio).hexdigest(): transcript
                for audio, transcript in transcripts.items()
            }
        )

    def transcribe(self, audio: bytes, *, locale: str) -> SttTranscript:
        del locale
        text = self.transcripts.get(hashlib.sha256(audio).hexdigest())
        return SttTranscript(available=text is not None, text=text)
