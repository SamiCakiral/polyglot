from polyglot.interfaces.http.app import create_app
from polyglot.modules.media.ports import (
    DeterministicTtsPort,
    TtsAvailability,
    TtsRequest,
    TtsVoice,
)


def test_tts_capability_contract_keeps_explicit_availability() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/media/tts/capabilities"]["get"]
    schema = document["components"]["schemas"]["TtsVoiceResponse"]

    assert operation["security"] == [{"SessionCookie": []}]
    assert {"voice_id", "language_tags", "formats", "limits", "availability"} <= schema[
        "properties"
    ].keys()


def test_retired_voice_never_selects_an_available_replacement() -> None:
    port = DeterministicTtsPort(
        voices=(TtsVoice("Bruno", "it-IT", TtsAvailability.AVAILABLE, "local-v1"),)
    )

    result = port.synthesize(TtsRequest("Ciao", "it-IT", "Alice", {}))

    assert result.voice_id == "Alice"
    assert result.availability is TtsAvailability.RETIRED
    assert result.audio is None
