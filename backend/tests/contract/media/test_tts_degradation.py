from uuid import UUID

import pytest
from pydantic import ValidationError

from polyglot.interfaces.http.app import create_app
from polyglot.interfaces.http.routes.media import SynthesizeSpeechRequest
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


def test_tts_request_accepts_exactly_one_public_or_private_source() -> None:
    direct = SynthesizeSpeechRequest(text="Ciao", locale="it-IT", voice_id="Alice")
    private = SynthesizeSpeechRequest(
        assessment_run_id=UUID("019fe015-0000-7000-8000-000000000001"),
        assessment_item_id=UUID("019fe015-0000-7000-8000-000000000002"),
        locale="it-IT",
        voice_id="Alice",
    )

    assert direct.text == "Ciao"
    assert private.text is None
    invalid_sources = (
        {},
        {"assessment_run_id": private.assessment_run_id},
        {"assessment_item_id": private.assessment_item_id},
        {
            "text": "Ciao",
            "assessment_run_id": private.assessment_run_id,
            "assessment_item_id": private.assessment_item_id,
        },
    )
    for source in invalid_sources:
        with pytest.raises(ValidationError):
            SynthesizeSpeechRequest(locale="it-IT", voice_id="Alice", **source)
