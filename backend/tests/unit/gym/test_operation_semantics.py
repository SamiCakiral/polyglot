import pytest

from polyglot.platform.errors import DomainError, ErrorCode

_CASES = {
    "GYM-01": (
        "Vorrei un caffe",
        (("un caffe", "un biglietto"),),
        "Vorrei un biglietto",
        {"slot_id": "object", "before_form": "un caffe", "after_form": "un biglietto"},
    ),
    "GYM-02": (
        "Posso entrare?",
        (("Posso", "Puo"),),
        "Puo entrare?",
        {
            "from_person": "first_singular",
            "to_person": "third_singular",
            "before_form": "Posso",
            "after_form": "Puo",
        },
    ),
    "GYM-03": (
        "C'e una camera",
        (("C'e una camera", "Ci sono due camere"),),
        "Ci sono due camere",
        {
            "from_number": "singular",
            "to_number": "plural",
            "before_form": "C'e una camera",
            "after_form": "Ci sono due camere",
        },
    ),
    "GYM-04": (
        "Ho fame",
        (("Ho", "Non ho"),),
        "Non ho fame",
        {"marker": "Non", "before_form": "Ho", "after_form": "Non ho"},
    ),
    "GYM-05": (
        "Il treno parte",
        (("Il treno parte", "Quando parte il treno?"),),
        "Quando parte il treno?",
        {
            "question_type": "when",
            "before_form": "Il treno parte",
            "after_form": "Quando parte il treno?",
        },
    ),
    "GYM-06": (
        "Prendo il treno",
        (("Prendo", "Ho preso"),),
        "Ho preso il treno",
        {
            "from_tense": "present",
            "to_tense": "past",
            "before_form": "Prendo",
            "after_form": "Ho preso",
        },
    ),
    "GYM-07": (
        "Prendo il treno",
        (("Prendo", "Devo prendere"),),
        "Devo prendere il treno",
        {
            "from_modality": "assertion",
            "to_modality": "obligation",
            "before_form": "Prendo",
            "after_form": "Devo prendere",
        },
    ),
    "GYM-08": (
        "Posso entrare?",
        (("Posso", "Puo"),),
        "Puo entrare?",
        {
            "from_register": "informal",
            "to_register": "formal",
            "before_form": "Posso",
            "after_form": "Puo",
        },
    ),
    "GYM-09": (
        "Io cerco il binario",
        (("Io cerco", "Lei cerca"),),
        "Lei cerca il binario",
        {
            "from_viewpoint": "speaker",
            "to_viewpoint": "addressee",
            "before_form": "Io cerco",
            "after_form": "Lei cerca",
        },
    ),
    "GYM-10": (
        "Prendo il biglietto",
        (("Prendo il biglietto", "Lo prendo"),),
        "Lo prendo",
        {
            "from_reference": "noun_phrase",
            "to_reference": "clitic",
            "before_form": "Prendo il biglietto",
            "after_form": "Lo prendo",
        },
    ),
    "GYM-11": (
        "Ho un biglietto. Salgo",
        ((". Salgo", ", quindi salgo"),),
        "Ho un biglietto, quindi salgo",
        {"connector_id": "quindi", "before_form": ". Salgo", "after_form": ", quindi salgo"},
    ),
    "GYM-12": (
        "Vorrei un biglietto",
        (("un biglietto", "un biglietto per Roma"),),
        "Vorrei un biglietto per Roma",
        {
            "direction": "expansion",
            "before_form": "un biglietto",
            "after_form": "un biglietto per Roma",
        },
    ),
    "GYM-13": (
        "Sono Sami",
        (("Sono Sami", "Ecco Sami"),),
        "Ecco Sami",
        {
            "source_frame": "sono_identity",
            "target_frame": "ecco_identification",
            "before_form": "Sono Sami",
            "after_form": "Ecco Sami",
        },
    ),
    "GYM-14": (
        "Vado prendere il treno",
        (("Vado prendere", "Sto per prendere"),),
        "Sto per prendere il treno",
        {
            "calque_id": "andare_infinitive",
            "repair_frame": "stare_per_infinitive",
            "before_form": "Vado prendere",
            "after_form": "Sto per prendere",
        },
    ),
    "GYM-15": (
        "Voglio un biglietto",
        (("Voglio", "Vorrei"), ("un biglietto", "un biglietto per Roma")),
        "Vorrei un biglietto per Roma",
        {"step_operation_ids": "GYM-08,GYM-12"},
    ),
}


def _semantics(operation_id: str, parameters=None):
    from polyglot.modules.exercises.gym.domain import OperationSemantics, operation_spec

    spec = operation_spec(operation_id)
    return OperationSemantics.create(
        kind=spec.name,
        prerequisite_kind=spec.prerequisite_kind,
        invariant_kind=spec.primary_invariant,
        parameters=_CASES[operation_id][3] if parameters is None else parameters,
    )


def _case(operation_id: str, semantics):
    from polyglot.modules.exercises.gym.domain import TransformationCase

    source, edits, output, _ = _CASES[operation_id]
    return TransformationCase.published(
        case_id=f"semantic:{operation_id}",
        revision_id=f"semantic:{operation_id}:v1",
        operation_id=operation_id,
        source_text=source,
        edits=edits,
        accepted_outputs=(output,),
        rejected_outputs=(source,),
        required_prerequisites=(f"prerequisite:{operation_id}",),
        invariants=(f"invariant:{operation_id}",),
        grammar_target_id=f"grammar:{operation_id}",
        lexical_support_ids=(),
        secondary_target_ids=(),
        distractor_target_ids=(),
        semantics=semantics,
    )


@pytest.mark.parametrize("operation_id", tuple(_CASES))
def test_each_operation_executes_its_own_semantic_contract(operation_id: str) -> None:
    from polyglot.modules.exercises.gym.domain import PrerequisiteGrant

    case = _case(operation_id, _semantics(operation_id))
    result = case.execute(grants=(PrerequisiteGrant.acquired(f"prerequisite:{operation_id}"),))

    assert result.output_text == _CASES[operation_id][2]
    assert result.executed_semantic == case.semantics.kind


@pytest.mark.parametrize("index", range(15))
def test_each_operation_rejects_a_neighbor_operations_semantics(index: int) -> None:
    operation_ids = tuple(_CASES)
    operation_id = operation_ids[index]
    hostile_semantics = _semantics(operation_ids[(index + 1) % len(operation_ids)])

    with pytest.raises(DomainError) as rejected:
        _case(operation_id, hostile_semantics)

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED


@pytest.mark.parametrize("operation_id", tuple(_CASES))
def test_each_operation_rejects_incomplete_semantic_constraints(operation_id: str) -> None:
    parameters = dict(_CASES[operation_id][3])
    parameters.pop(next(iter(parameters)))

    with pytest.raises(DomainError) as rejected:
        _case(operation_id, _semantics(operation_id, parameters))

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED
