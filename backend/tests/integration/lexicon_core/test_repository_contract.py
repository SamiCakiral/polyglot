from polyglot.modules.lexicon.core.persistence import (
    LexiconRepository,
    lexical_encounters,
    mention_resolutions,
)


def test_repository_is_bound_to_personal_append_only_tables() -> None:
    assert lexical_encounters.schema == "lexicon"
    assert mention_resolutions.schema == "lexicon"
    assert {
        "record_encounter",
        "resolve_mention",
        "delete_private_context",
        "get_command_receipt",
        "save_command_receipt",
    } <= set(dir(LexiconRepository))
