import json
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from polyglot.modules.generation.providers import ChatProvider, ChatRequest
from polyglot.platform.errors import DomainError, ErrorCode

MODEL = "qwen/qwen3.6-35b-a3b"


class JudgementStatus(StrEnum):
    EVALUATED = "evaluated"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class ErrorObservation:
    code: str
    start: int | None
    end: int | None


@dataclass(frozen=True, slots=True)
class EvaluationTask:
    prompt: str
    learner_response: str
    criteria: tuple[str, ...]
    allowed_skill_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlacementJudgementDraft:
    status: JudgementStatus
    criterion_scores: tuple[tuple[str, int], ...]
    demonstrated_skill_refs: tuple[str, ...]
    error_observations: tuple[ErrorObservation, ...]
    fatal_error_codes: tuple[str, ...]
    confidence: float
    short_rationale: str


class PlacementEvaluator:
    def __init__(self, provider: ChatProvider) -> None:
        self._provider = provider

    async def evaluate(self, task: EvaluationTask) -> PlacementJudgementDraft:
        schema = {
            "status": "evaluated | not_evaluable",
            "criterion_scores": {criterion: "integer 0..4" for criterion in task.criteria},
            "demonstrated_skill_refs": list(task.allowed_skill_refs),
            "error_observations": [{"code": "string", "start": 0, "end": 0}],
            "fatal_error_codes": ["string"],
            "confidence": "number 0..1",
            "short_rationale": "string <= 240 chars",
        }
        result = await self._provider.complete(
            ChatRequest(
                model=MODEL,
                messages=(
                    (
                        "system",
                        (
                            "Évalue uniquement la réponse avec la grille fournie. "
                            "N'infère aucun niveau global. Réponds par un seul objet JSON strict, "
                            f"sans markdown, de forme {json.dumps(schema, ensure_ascii=False)}"
                        ),
                    ),
                    (
                        "user",
                        json.dumps(
                            {
                                "task": task.prompt,
                                "response": task.learner_response,
                                "criteria": task.criteria,
                                "allowed_skill_refs": task.allowed_skill_refs,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ),
                max_output_tokens=800,
            )
        )
        return self._parse(result.message, task)

    @staticmethod
    def _parse(message: str, task: EvaluationTask) -> PlacementJudgementDraft:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError as error:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False) from error
        expected = {
            "status",
            "criterion_scores",
            "demonstrated_skill_refs",
            "error_observations",
            "fatal_error_codes",
            "confidence",
            "short_rationale",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        scores = payload["criterion_scores"]
        skills = payload["demonstrated_skill_refs"]
        errors = payload["error_observations"]
        rationale = payload["short_rationale"]
        confidence = payload["confidence"]
        if (
            not isinstance(scores, dict)
            or set(scores) != set(task.criteria)
            or any(not isinstance(value, int) or not 0 <= value <= 4 for value in scores.values())
            or not isinstance(skills, list)
            or any(skill not in task.allowed_skill_refs for skill in skills)
            or not isinstance(errors, list)
            or not isinstance(rationale, str)
            or len(rationale) > 240
            or not isinstance(confidence, int | float)
            or isinstance(confidence, bool)
            or not 0 <= confidence <= 1
        ):
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        parsed_errors: list[ErrorObservation] = []
        for item in errors:
            if not isinstance(item, dict) or set(item) != {"code", "start", "end"}:
                raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
            parsed_errors.append(
                ErrorObservation(
                    cast(str, item["code"]),
                    cast(int | None, item["start"]),
                    cast(int | None, item["end"]),
                )
            )
        try:
            status = JudgementStatus(payload["status"])
        except (ValueError, TypeError) as error:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False) from error
        fatal = payload["fatal_error_codes"]
        if not isinstance(fatal, list) or not all(isinstance(item, str) for item in fatal):
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        return PlacementJudgementDraft(
            status,
            tuple(sorted(scores.items())),
            tuple(skills),
            tuple(parsed_errors),
            tuple(fatal),
            float(confidence),
            rationale,
        )
