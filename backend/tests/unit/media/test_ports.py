from dataclasses import dataclass, field
from pathlib import Path

from polyglot.modules.media.ports import (
    DeterministicSttPort,
    DeterministicTtsPort,
    MacOSTtsPort,
    TtsAvailability,
    TtsRequest,
    TtsVoice,
)


def test_tts_never_substitutes_a_retired_voice_and_caches_exact_request() -> None:
    port = DeterministicTtsPort(
        voices=(
            TtsVoice("alice-it", "it-IT", TtsAvailability.AVAILABLE, "fixture-v1"),
            TtsVoice("bruno-it", "it-IT", TtsAvailability.AVAILABLE, "fixture-v1"),
        )
    )
    request = TtsRequest("Ciao", "it-IT", "alice-it", {"speed": "normal"})

    first = port.synthesize(request)
    second = port.synthesize(request)
    retired = port.withdraw_voice("alice-it").synthesize(request)

    assert first.availability is TtsAvailability.AVAILABLE
    assert first.audio is not None
    assert first.cache_key == second.cache_key
    assert first.audio == second.audio
    assert retired.availability is TtsAvailability.RETIRED
    assert retired.audio is None
    assert retired.voice_id == "alice-it"


def test_provider_absence_is_explicit_without_a_voice_fallback() -> None:
    request = TtsRequest("Ciao", "it-IT", "alice-it", {})
    unavailable = DeterministicTtsPort.unavailable().synthesize(request)

    assert unavailable.availability is TtsAvailability.TEMPORARILY_UNAVAILABLE
    assert unavailable.audio is None
    assert unavailable.voice_id == "alice-it"


def test_stt_fake_uses_fixture_audio_without_provider() -> None:
    audio = b"FX-MEDIA deterministic audio bytes\n"
    port = DeterministicSttPort.from_transcripts({audio: "Ciao, come stai?"})

    transcript = port.transcribe(audio, locale="it-IT")
    missing = port.transcribe(b"missing", locale="it-IT")

    assert transcript.available is True
    assert transcript.text == "Ciao, come stai?"
    assert missing.available is False
    assert missing.text is None


@dataclass
class RecordingRunner:
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, command: tuple[str, ...]) -> None:
        self.calls.append(command)
        Path(command[-1]).write_bytes(b"simulated-mp3")


def test_macos_adapter_is_injectable_and_does_not_need_macos(tmp_path: Path) -> None:
    runner = RecordingRunner()
    port = MacOSTtsPort(
        voices=(TtsVoice("alice-it", "it-IT", TtsAvailability.AVAILABLE, "local-v1"),),
        cache_dir=tmp_path,
        runner=runner,
    )

    result = port.synthesize(TtsRequest("Ciao", "it-IT", "alice-it", {}))

    assert result.audio == b"simulated-mp3"
    assert len(runner.calls) == 2
    assert runner.calls[0][0] == "say"
    assert runner.calls[1][0] == "ffmpeg"
