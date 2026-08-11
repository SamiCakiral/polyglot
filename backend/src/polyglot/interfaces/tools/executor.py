from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from polyglot.interfaces.tools.registry import SEMVER, TOOL_REGISTRY, ToolDefinition
from polyglot.platform.fingerprint import canonical_json_bytes, canonical_json_fingerprint
from polyglot.platform.json_types import JsonValue


class ToolInvocationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ToolScope:
    pack_revision_id: UUID | None = None
    profile_id: UUID | None = None
    job_id: UUID | None = None
    mandate_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    tool_name: str
    tool_version: str
    invocation_id: UUID
    actor_id: UUID
    actor_role: str
    scope: ToolScope
    idempotency_key: str
    expected_version: int | None
    input: dict[str, JsonValue]
    correlation_id: UUID
    causation_id: UUID | None
    policy_revisions: dict[str, str]


@dataclass(frozen=True, slots=True)
class ToolFailure:
    code: str
    retryable: bool = False
    field_path: str | None = None
    details_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolResult:
    invocation_id: UUID
    tool_version: str
    status: ToolInvocationStatus
    output: dict[str, JsonValue] | None
    error: ToolFailure | None
    output_schema_version: int
    provenance_id: UUID
    started_at: datetime
    finished_at: datetime
    output_fingerprint: str


ToolHandler = Callable[[ToolInvocation, ToolDefinition], Awaitable[dict[str, JsonValue]]]


class ToolExecutor:
    def __init__(
        self,
        handlers: Mapping[str, ToolHandler],
        *,
        now: Callable[[], datetime],
        provenance_id: Callable[[], UUID],
    ) -> None:
        self._handlers = handlers
        self._now = now
        self._provenance_id = provenance_id

    async def invoke(self, invocation: ToolInvocation) -> ToolResult:
        started_at = self._now()
        definition = TOOL_REGISTRY.get(invocation.tool_name)
        failure = self._validate(invocation, definition)
        if failure is not None or definition is None:
            return self._failure(invocation, failure or ToolFailure("tool_not_allowed"), started_at)
        handler = self._handlers.get(definition.name)
        if handler is None:
            return self._failure(
                invocation, ToolFailure("dependency_unavailable", retryable=False), started_at
            )
        try:
            output = await asyncio.wait_for(
                handler(invocation, definition), timeout=definition.timeout_ms / 1000
            )
        except TimeoutError:
            return self._failure(invocation, ToolFailure("timeout"), started_at)
        except ToolRejected as error:
            return self._failure(invocation, error.failure, started_at)
        except Exception:
            return self._failure(invocation, ToolFailure("internal_error"), started_at)
        if len(canonical_json_bytes(output)) > definition.max_output_bytes:
            return self._failure(invocation, ToolFailure("size_limit_exceeded"), started_at)
        output_failure = self._schema_failure(output, definition.output_schema(), "output")
        if output_failure is not None:
            return self._failure(
                invocation,
                output_failure,
                started_at,
            )
        finished_at = self._now()
        return ToolResult(
            invocation.invocation_id,
            definition.version,
            ToolInvocationStatus.SUCCEEDED,
            output,
            None,
            1,
            self._provenance_id(),
            started_at,
            finished_at,
            canonical_json_fingerprint(output),
        )

    @staticmethod
    def _validate(
        invocation: ToolInvocation, definition: ToolDefinition | None
    ) -> ToolFailure | None:
        if definition is None:
            return ToolFailure("tool_not_allowed", field_path="tool_name")
        if (
            not SEMVER.fullmatch(invocation.tool_version)
            or invocation.tool_version != definition.version
        ):
            return ToolFailure("tool_schema_invalid", field_path="tool_version")
        if invocation.actor_role not in definition.roles:
            return ToolFailure("tool_not_allowed", field_path="actor_role")
        if definition.mutating and not invocation.idempotency_key:
            return ToolFailure("tool_schema_invalid", field_path="idempotency_key")
        schema_failure = ToolExecutor._schema_failure(
            invocation.input, definition.input_schema(), "input"
        )
        if schema_failure is not None:
            return schema_failure
        if len(canonical_json_bytes(invocation.input)) > definition.max_input_bytes:
            return ToolFailure("size_limit_exceeded", field_path="input")
        if definition.name == "catalogue.list_targets":
            limit = invocation.input.get("limit", 100)
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
                return ToolFailure("size_limit_exceeded", field_path="input.limit")
        return None

    @staticmethod
    def _schema_failure(
        payload: dict[str, JsonValue], schema: dict[str, JsonValue], prefix: str
    ) -> ToolFailure | None:
        errors = sorted(
            Draft202012Validator(schema).iter_errors(payload),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        if not errors:
            return None
        path = ".".join(str(part) for part in errors[0].absolute_path)
        return ToolFailure(
            "tool_schema_invalid",
            field_path=prefix if not path else f"{prefix}.{path}",
        )

    def _failure(
        self, invocation: ToolInvocation, failure: ToolFailure, started_at: datetime
    ) -> ToolResult:
        finished_at = self._now()
        error_payload: dict[str, JsonValue] = {
            "code": failure.code,
            "retryable": failure.retryable,
            "field_path": failure.field_path,
            "details_codes": list(failure.details_codes),
        }
        return ToolResult(
            invocation.invocation_id,
            invocation.tool_version,
            ToolInvocationStatus.REJECTED,
            None,
            failure,
            1,
            self._provenance_id(),
            started_at,
            finished_at,
            canonical_json_fingerprint(error_payload),
        )


class ToolRejected(Exception):
    def __init__(self, failure: ToolFailure) -> None:
        super().__init__(failure.code)
        self.failure = failure
