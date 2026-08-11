from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from polyglot.interfaces.tools.executor import (
    ToolFailure,
    ToolHandler,
    ToolInvocation,
    ToolRejected,
)
from polyglot.interfaces.tools.registry import TOOL_DEFINITIONS, ToolDefinition
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.json_types import JsonValue


class DeterministicToolHandlers:
    def __init__(self, new_id: Callable[[], UUID]) -> None:
        self._new_id = new_id

    def handlers(self) -> dict[str, ToolHandler]:
        return {definition.name: self._handle for definition in TOOL_DEFINITIONS}

    async def _handle(
        self, invocation: ToolInvocation, definition: ToolDefinition
    ) -> dict[str, JsonValue]:
        payload = invocation.input
        if definition.name == "profile.read_authorized":
            groups = payload["field_groups"]
            if not isinstance(groups, list) or any(
                item
                not in {
                    "goals",
                    "constraints",
                    "mastery_summary",
                    "due_summary",
                    "module_position",
                }
                for item in groups
            ):
                raise ToolRejected(ToolFailure("field_group_forbidden"))
            return {
                "profile_id": payload["profile_id"],
                "field_groups": groups,
                "pseudonymized": True,
                "cutoff": "fixture-clock",
            }
        if definition.name == "catalogue.list_targets":
            return {"targets": [], "next_cursor": None, "stable": True}
        if definition.name == "lexicon.read_session_scope":
            return {"senses": [], "snapshot_id": payload["planning_snapshot_id"]}
        if definition.name == "exercise.get_blueprint":
            return {
                "primitive_id": payload["primitive_id"],
                "contract_version": payload["primitive_contract_version"],
                "correction_strategies": ["deterministic", "rubric"],
                "publish_capability": False,
            }
        if definition.name == "content.validate_draft":
            return {
                "validation_report_id": str(self._new_id()),
                "decision": "human_required",
                "findings": [],
                "report_truncated": False,
            }
        if definition.name == "quality.report_ambiguity":
            return {
                "quality_report_id": str(self._new_id()),
                "status": "open",
                "visibility": (
                    "private" if payload.get("private_context_consent") is True else "editorial"
                ),
                "deduplication_fingerprint": canonical_json_fingerprint(payload),
            }
        if definition.name == "progress.explain_recommendation":
            return {
                "recommendation_id": payload["recommendation_id"],
                "reason_codes": ["evidence_freshness"],
                "facts": [],
                "alternatives": [],
            }
        draft_type = {
            "exercise.submit_draft": "exercise",
            "curriculum.submit_module_draft": "module",
            "curriculum.submit_day_draft": "day",
            "correction.submit_structured_draft": "correction",
        }.get(definition.name)
        if draft_type is not None:
            return {
                "draft_id": str(self._new_id()),
                "draft_type": draft_type,
                "revision": 1,
                "status": "draft",
                "findings": [],
                "checksum": canonical_json_fingerprint(payload),
                "publish_capability": False,
                "mastery_capability": False,
            }
        raise ToolRejected(ToolFailure("tool_not_allowed"))
