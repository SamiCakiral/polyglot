from dataclasses import FrozenInstanceError

import pytest

from polyglot.platform.errors import DomainError, ErrorCode


def _case(operation: str, source: str, edits: tuple[tuple[str, str], ...], output: str):
    from polyglot.modules.exercises.gym.domain import TransformationCase

    return TransformationCase.published(
        case_id=f"case:{operation.lower()}",
        revision_id=f"revision:{operation.lower()}:v1",
        operation_id=operation,
        source_text=source,
        edits=edits,
        accepted_outputs=(output,),
        rejected_outputs=(source,),
        required_prerequisites=(f"prerequisite:{operation.lower()}",),
        invariants=("communicative_intention",),
        grammar_target_id="grammar:target",
        lexical_support_ids=("lexicon:support",),
    )


def test_registry_closes_the_fifteen_normative_operations() -> None:
    from polyglot.modules.exercises.gym.domain import GYM_OPERATION_IDS, operation_spec

    assert GYM_OPERATION_IDS == tuple(f"GYM-{index:02d}" for index in range(1, 16))
    assert operation_spec("GYM-01").name == "lexical_substitution"
    assert operation_spec("GYM-15").primary_invariant == "declared_invariants"

    with pytest.raises(DomainError) as rejected:
        operation_spec("GYM-16")

    assert rejected.value.code is ErrorCode.MODE_UNSUPPORTED


@pytest.mark.parametrize(
    ("operation", "source", "edits", "expected"),
    (
        ("GYM-01", "Vorrei un caffe", (("un caffe", "un biglietto"),), "Vorrei un biglietto"),
        ("GYM-02", "Posso entrare?", (("Posso", "Puo"),), "Puo entrare?"),
        ("GYM-04", "Ho fame", (("Ho", "Non ho"),), "Non ho fame"),
        ("GYM-06", "Prendo il treno", (("Prendo", "Ho preso"),), "Ho preso il treno"),
        ("GYM-08", "Posso entrare?", (("Posso", "Puo"),), "Puo entrare?"),
        (
            "GYM-12",
            "Vorrei un biglietto",
            (("un biglietto", "un biglietto per Roma, per favore"),),
            "Vorrei un biglietto per Roma, per favore",
        ),
        (
            "GYM-14",
            "Vado prendere il treno",
            (("Vado prendere", "Sto per prendere"),),
            "Sto per prendere il treno",
        ),
    ),
)
def test_published_transformations_execute_their_declared_edits(
    operation: str,
    source: str,
    edits: tuple[tuple[str, str], ...],
    expected: str,
) -> None:
    from polyglot.modules.exercises.gym.domain import PrerequisiteGrant, execute_transformation

    case = _case(operation, source, edits, expected)
    original_edits = edits

    result = execute_transformation(
        case,
        grants=(
            PrerequisiteGrant.acquired(f"prerequisite:{operation.lower()}"),
        ),
    )

    assert result.output_text == expected
    assert result.operation_id == operation
    assert result.preserved_invariants == ("communicative_intention",)
    assert case.edits == original_edits
    assert case.source_text == source


def test_missing_prerequisite_blocks_before_any_transformation() -> None:
    from polyglot.modules.exercises.gym.domain import execute_transformation

    case = _case(
        "GYM-04",
        "Ho fame",
        (("Ho", "Non ho"),),
        "Non ho fame",
    )

    with pytest.raises(DomainError) as rejected:
        execute_transformation(case, grants=())

    assert rejected.value.code is ErrorCode.PREREQUISITE_MISSING
    assert rejected.value.details == {"missing": ["prerequisite:gym-04"]}
    assert case.source_text == "Ho fame"


def test_explicit_non_evaluated_support_satisfies_a_prerequisite() -> None:
    from polyglot.modules.exercises.gym.domain import PrerequisiteGrant, execute_transformation

    case = _case(
        "GYM-01",
        "Vorrei un caffe",
        (("un caffe", "un biglietto"),),
        "Vorrei un biglietto",
    )
    result = execute_transformation(
        case,
        grants=(PrerequisiteGrant.support("prerequisite:gym-01"),),
    )

    assert result.non_evaluated_support == ("prerequisite:gym-01",)


def test_case_is_deeply_immutable_and_rejects_unpublished_output() -> None:
    from polyglot.modules.exercises.gym.domain import PrerequisiteGrant, TransformationCase

    edits = [["Sono Sami", "Ecco Sami"]]
    outputs = ["Ecco Sami"]
    case = TransformationCase.published(
        case_id="case:immutable",
        revision_id="revision:immutable:v1",
        operation_id="GYM-13",
        source_text="Sono Sami",
        edits=edits,
        accepted_outputs=outputs,
        rejected_outputs=("Sami sono",),
        required_prerequisites=("contrast:sono-ecco",),
        invariants=("identity",),
        grammar_target_id="grammar:identity",
        lexical_support_ids=(),
    )

    edits[0][1] = "corrupted"
    outputs.clear()

    assert case.edits == (("Sono Sami", "Ecco Sami"),)
    assert case.accepted_outputs == ("Ecco Sami",)
    with pytest.raises(FrozenInstanceError):
        case.source_text = "mutated"  # type: ignore[misc]
    with pytest.raises(DomainError) as rejected:
        case.execute(
            grants=(PrerequisiteGrant.acquired("contrast:sono-ecco"),),
            proposed_output="Sami ecco",
        )
    assert rejected.value.code is ErrorCode.VALIDATION_FAILED


def test_calque_repair_rejects_the_forbidden_andare_plus_infinitive_output() -> None:
    from polyglot.modules.exercises.gym.domain import PrerequisiteGrant

    case = _case(
        "GYM-14",
        "Vado prendere il treno",
        (("Vado prendere", "Sto per prendere"),),
        "Sto per prendere il treno",
    )

    with pytest.raises(DomainError) as rejected:
        case.execute(
            grants=(PrerequisiteGrant.acquired("prerequisite:gym-14"),),
            proposed_output="Vado a prendere il treno",
        )

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED

