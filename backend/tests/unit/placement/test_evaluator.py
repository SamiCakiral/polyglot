import json

import pytest

from polyglot.modules.generation.providers import ChatResult
from polyglot.modules.placement.evaluator import EvaluationTask, PlacementEvaluator
from polyglot.platform.errors import DomainError


class Provider:
    code = "test"
    model = "qwen/qwen3.6-35b-a3b"

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls = 0

    async def complete(self, request: object) -> ChatResult:
        self.calls += 1
        return ChatResult(json.dumps(self.payload), 1, 1)


def _task() -> EvaluationTask:
    return EvaluationTask(
        prompt="Présentez-vous.",
        learner_response="Mi chiamo Sami.",
        criteria=("task", "grammar"),
        allowed_skill_refs=("writing",),
    )


@pytest.mark.asyncio
async def test_evaluator_accepts_only_closed_schema() -> None:
    provider = Provider(
        {
            "status": "evaluated",
            "criterion_scores": {"task": 4, "grammar": 3},
            "demonstrated_skill_refs": ["writing"],
            "error_observations": [],
            "fatal_error_codes": [],
            "confidence": 0.8,
            "short_rationale": "Réponse adéquate et compréhensible.",
        }
    )
    result = await PlacementEvaluator(provider).evaluate(_task())
    assert result.confidence == 0.8
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_evaluator_rejects_extra_keys() -> None:
    provider = Provider({"status": "evaluated", "reasoning": "private"})
    with pytest.raises(DomainError):
        await PlacementEvaluator(provider).evaluate(_task())
