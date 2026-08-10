from polyglot.modules.media.shadowing import ShadowingAvailability, ShadowingPrompt


def test_shadowing_remains_available_as_transcript_alternative_when_audio_is_absent() -> None:
    prompt = ShadowingPrompt.from_fixture(audio=None, transcript="Ciao, come stai?")

    assert prompt.availability is ShadowingAvailability.ALTERNATIVE_AVAILABLE
    assert prompt.transcript == "Ciao, come stai?"
    assert prompt.evaluable is False
