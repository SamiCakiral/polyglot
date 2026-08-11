from polyglot.modules.catalogue.core.italian_grammar import ITALIAN_GRAMMAR_TOOLBOX


def test_italian_toolbox_covers_all_families_and_priority_moulds() -> None:
    toolbox = ITALIAN_GRAMMAR_TOOLBOX

    assert toolbox.version == "it-grammar-1.0.0"
    assert len(toolbox.families) == 18
    assert len(toolbox.realizations) == 30
    assert len(toolbox.priority_realization_codes) == 30
    assert set(toolbox.priority_realization_codes) == {
        item.realization_code for item in toolbox.realizations
    }


def test_each_realization_is_teachable_then_transformable() -> None:
    for item in ITALIAN_GRAMMAR_TOOLBOX.realizations:
        assert item.function_code
        assert item.support_template
        assert item.target_template
        assert item.examples
        assert item.compatible_primitives
        assert "EX-EXPOSE-01" in item.compatible_primitives
        assert "EX-TRANSFORM-01" in item.compatible_primitives
        assert item.transformations


def test_french_italian_contrasts_keep_known_traps_explicit() -> None:
    by_code = {item.realization_code: item for item in ITALIAN_GRAMMAR_TOOLBOX.realizations}

    assert "accent" in " ".join(by_code["IT-GRAM-004"].pitfalls).casefold()
    assert "singulier" in " ".join(by_code["IT-GRAM-027"].pitfalls).casefold()
    assert "subjonctif" in " ".join(by_code["IT-GRAM-030"].pitfalls).casefold()
