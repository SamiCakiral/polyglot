from __future__ import annotations

# ruff: noqa: E501
import json
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.interfaces.tools.executor import (
    ToolExecutor,
    ToolFailure,
    ToolInvocation,
    ToolInvocationStatus,
    ToolResult,
    ToolScope,
)
from polyglot.interfaces.tools.registry import TOOL_REGISTRY
from polyglot.modules.generation.application import (
    AuthoringArtifactView,
    GenerationJobView,
    RequestGenerationJob,
)
from polyglot.modules.generation.orchestration import (
    build_generation_messages,
    parse_generation_plan,
)
from polyglot.modules.generation.providers import ChatProvider, ChatRequest
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.records import CommandReceipt
from polyglot.platform.persistence.repositories import SqlCommandReceiptStore


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _uuid(value: object) -> UUID:
    return UUID(str(value))


class SqlGenerationService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        executor: ToolExecutor,
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._sessions = sessions
        self._executor = executor
        self._clock = clock or SystemClock()
        self._ids = id_generator or Uuid7Generator(self._clock)

    async def request_job(
        self,
        actor_id: UUID,
        command: RequestGenerationJob,
        *,
        idempotency_key: str,
    ) -> GenerationJobView:
        now = self._clock.now()
        if command.max_attempts != 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if command.provider_code != "lm_studio" or command.model_code != "qwen/qwen3.6-35b-a3b":
            raise DomainError(ErrorCode.PROVIDER_UNAVAILABLE, retryable=False)
        invalid_tools = False
        for item in command.tool_allowlist:
            name, separator, version = item.partition("@")
            definition = TOOL_REGISTRY.get(name)
            if not separator or definition is None or version != definition.version:
                invalid_tools = True
                break
        if not command.tool_allowlist or invalid_tools:
            raise DomainError(ErrorCode.TOOL_NOT_ALLOWED)
        fingerprint_payload: dict[str, JsonValue] = {
            "task_type": command.task_type,
            "task_input": command.task_input,
            "tool_allowlist": list(command.tool_allowlist),
            "provider_code": command.provider_code,
            "model_code": command.model_code,
            "prompt_revision": command.prompt_revision,
            "max_attempts": command.max_attempts,
            "max_input_tokens": command.max_input_tokens,
            "max_output_tokens": command.max_output_tokens,
            "max_cost_micros": command.max_cost_micros,
        }
        fingerprint = canonical_json_fingerprint(fingerprint_payload)
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            existing = (
                (
                    await session.execute(
                        text(
                            "SELECT j.job_id,j.request_fingerprint FROM platform.jobs j "
                            "WHERE j.requested_by_actor_id=:actor AND j.job_type='generation' "
                            "AND j.idempotency_key=:key"
                        ),
                        {"actor": actor_id, "key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return await self._read_job(session, _uuid(existing["job_id"]))
            job_id = self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO platform.jobs "
                    "(job_id,job_type,requested_by_actor_id,profile_id,status,idempotency_key,"
                    "request_fingerprint,correlation_id,payload_schema_version,requested_at,"
                    "progress_completed,progress_total,version) VALUES "
                    "(:job,'generation',:actor,NULL,'requested',:key,:fingerprint,:correlation,1,"
                    ":now,0,1,1)"
                ),
                {
                    "job": job_id,
                    "actor": actor_id,
                    "key": idempotency_key,
                    "fingerprint": fingerprint,
                    "correlation": self._ids.new(),
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO generation.generation_jobs "
                    "(job_id,owner_account_id,task_type,task_input,tool_allowlist,provider_code,"
                    "model_code,prompt_revision,max_attempts,max_input_tokens,max_output_tokens,"
                    "max_cost_micros,result_draft_id,created_at) VALUES "
                    "(:job,:actor,:task,CAST(:input AS jsonb),:tools,:provider,:model,:prompt,"
                    ":attempts,:input_tokens,:output_tokens,:cost,NULL,:now)"
                ),
                {
                    "job": job_id,
                    "actor": actor_id,
                    "task": command.task_type,
                    "input": _json(command.task_input),
                    "tools": list(command.tool_allowlist),
                    "provider": command.provider_code,
                    "model": command.model_code,
                    "prompt": command.prompt_revision,
                    "attempts": command.max_attempts,
                    "input_tokens": command.max_input_tokens,
                    "output_tokens": command.max_output_tokens,
                    "cost": command.max_cost_micros,
                    "now": now,
                },
            )
            return await self._read_job(session, job_id)

    async def get_job(self, actor_id: UUID, job_id: UUID) -> GenerationJobView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            return await self._read_job(session, job_id)

    async def cancel_job(
        self,
        actor_id: UUID,
        job_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> GenerationJobView:
        now = self._clock.now()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            receipt = CommandReceipt(
                self._ids.new(),
                "generation.cancel_job",
                actor_id,
                "generation_job",
                job_id,
                idempotency_key,
                canonical_json_fingerprint({"job_id": str(job_id)}),
                expected_version,
                now,
                None,
                None,
                "started",
                now + timedelta(hours=24),
            )
            reservation = await SqlCommandReceiptStore(session).reserve(receipt)
            if not reservation.created:
                if reservation.receipt.status != "succeeded":
                    raise DomainError(ErrorCode.RESPONSE_CONFLICT)
                return await self._read_job(session, job_id)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT status,version FROM platform.jobs "
                            "WHERE job_id=:job AND requested_by_actor_id=:actor FOR UPDATE"
                        ),
                        {"job": job_id, "actor": actor_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if int(row["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if row["status"] not in {"requested", "queued", "running"}:
                raise DomainError(ErrorCode.JOB_NOT_CANCELLABLE)
            status = "cancel_requested" if row["status"] == "running" else "cancelled"
            await session.execute(
                text(
                    "UPDATE platform.jobs SET status=CAST(:status AS varchar),cancel_requested_at=:now,"
                    "finished_at=CASE WHEN CAST(:status AS varchar)='cancelled' "
                    "THEN :now ELSE finished_at END,"
                    "version=version+1 WHERE job_id=:job"
                ),
                {"status": status, "now": now, "job": job_id},
            )
            view = await self._read_job(session, job_id)
            await SqlCommandReceiptStore(session).complete(
                command_id=reservation.receipt.command_id,
                status="succeeded",
                result_ref=job_id,
                result_payload={"resource_id": str(job_id), "version": view.version},
            )
            return view

    async def process_next_job(self, provider: ChatProvider) -> GenerationJobView | None:
        claimed = await self._claim_next_job()
        if claimed is None:
            return None
        job_id = _uuid(claimed["job_id"])
        actor_id = _uuid(claimed["owner_account_id"])
        started_at = self._clock.now()
        input_tokens = 0
        output_tokens = 0
        artifact_id: UUID | None = None
        error_code: str | None = None
        try:
            if claimed["provider_code"] != provider.code or claimed["model_code"] != provider.model:
                raise DomainError(ErrorCode.PROVIDER_UNAVAILABLE, retryable=False)
            allowlist = tuple(str(item) for item in cast(list[object], claimed["tool_allowlist"]))
            task_input = cast(dict[str, JsonValue], claimed["task_input"])
            max_input_tokens = cast(int, claimed["max_input_tokens"])
            max_output_tokens = cast(int, claimed["max_output_tokens"])
            messages = build_generation_messages(
                task_type=str(claimed["task_type"]),
                task_input=task_input,
                tool_allowlist=allowlist,
            )
            chat = await provider.complete(
                ChatRequest(
                    provider.model,
                    messages,
                    max_output_tokens,
                )
            )
            input_tokens = chat.input_tokens
            output_tokens = chat.output_tokens
            if input_tokens > max_input_tokens or output_tokens > max_output_tokens:
                raise DomainError(ErrorCode.BUDGET_EXCEEDED, retryable=False)
            plan = parse_generation_plan(chat.message, allowlist)
            role = await self._actor_role(actor_id, plan.tool_name)
            invocation = ToolInvocation(
                plan.tool_name,
                plan.tool_version,
                self._ids.new(),
                actor_id,
                role,
                ToolScope(job_id=job_id),
                f"generation:{job_id}:attempt:1",
                None,
                plan.input,
                self._ids.new(),
                job_id,
                {"prompt": str(claimed["prompt_revision"])},
            )
            result = await self.invoke_tool(invocation)
            if result.status is not ToolInvocationStatus.SUCCEEDED or result.output is None:
                code = result.error.code if result.error is not None else "internal_error"
                raise DomainError(code, retryable=False)
            artifact_id = self._artifact_id(result.output)
        except DomainError as error:
            error_code = error.code.value
        except Exception:
            error_code = ErrorCode.INTERNAL_ERROR.value
        return await self._finish_generation_job(
            claimed,
            started_at=started_at,
            artifact_id=artifact_id,
            error_code=error_code,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def invoke_tool(self, invocation: ToolInvocation) -> ToolResult:
        fingerprint_payload: dict[str, JsonValue] = {
            "tool_name": invocation.tool_name,
            "tool_version": invocation.tool_version,
            "actor_role": invocation.actor_role,
            "scope": {
                "pack_revision_id": None
                if invocation.scope.pack_revision_id is None
                else str(invocation.scope.pack_revision_id),
                "profile_id": None
                if invocation.scope.profile_id is None
                else str(invocation.scope.profile_id),
                "job_id": None if invocation.scope.job_id is None else str(invocation.scope.job_id),
                "mandate_id": None
                if invocation.scope.mandate_id is None
                else str(invocation.scope.mandate_id),
            },
            "expected_version": invocation.expected_version,
            "input": invocation.input,
        }
        fingerprint = canonical_json_fingerprint(fingerprint_payload)
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, invocation.actor_id)
            existing = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM generation.tool_invocations "
                            "WHERE owner_account_id=:actor AND tool_name=:tool AND idempotency_key=:key"
                        ),
                        {
                            "actor": invocation.actor_id,
                            "tool": invocation.tool_name,
                            "key": invocation.idempotency_key,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return self._stored_tool_result(existing)
            result = await self._executor.invoke(invocation)
            definition = TOOL_REGISTRY.get(invocation.tool_name)
            if definition is None:
                raise DomainError(ErrorCode.TOOL_NOT_ALLOWED)
            tool_revision_id = await session.scalar(
                text(
                    "SELECT tool_revision_id FROM generation.tool_revisions "
                    "WHERE tool_name=:tool AND tool_version=:version"
                ),
                {"tool": invocation.tool_name, "version": invocation.tool_version},
            )
            if tool_revision_id is None:
                raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
            scope = {
                "pack_revision_id": None
                if invocation.scope.pack_revision_id is None
                else str(invocation.scope.pack_revision_id),
                "profile_id": None
                if invocation.scope.profile_id is None
                else str(invocation.scope.profile_id),
                "job_id": None if invocation.scope.job_id is None else str(invocation.scope.job_id),
                "mandate_id": None
                if invocation.scope.mandate_id is None
                else str(invocation.scope.mandate_id),
            }
            error_payload = None
            if result.error is not None:
                error_payload = {
                    "code": result.error.code,
                    "retryable": result.error.retryable,
                    "field_path": result.error.field_path,
                    "details_codes": list(result.error.details_codes),
                }
            await session.execute(
                text(
                    "INSERT INTO platform.provenance_records "
                    "(provenance_id,source_type,source_ref,created_by_actor_id,tool_revision_id,"
                    "model_code,prompt_revision_id,transformation_chain,input_fingerprint,created_at) "
                    "VALUES (:provenance,'tool',:source_ref,:actor,:revision,NULL,NULL,"
                    "CAST(:chain AS jsonb),:fingerprint,:created_at) ON CONFLICT DO NOTHING"
                ),
                {
                    "provenance": result.provenance_id,
                    "source_ref": f"tool:{invocation.tool_name}@{invocation.tool_version}",
                    "actor": invocation.actor_id,
                    "revision": tool_revision_id,
                    "chain": _json(
                        [
                            {
                                "kind": "tool_invocation",
                                "invocation_id": str(invocation.invocation_id),
                            }
                        ]
                    ),
                    "fingerprint": fingerprint,
                    "created_at": result.finished_at,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO generation.tool_invocations "
                    "(invocation_id,owner_account_id,tool_revision_id,tool_name,actor_role,scope,"
                    "idempotency_key,request_fingerprint,input_payload,status,output_payload,error_payload,"
                    "output_fingerprint,provenance_id,correlation_id,causation_id,started_at,finished_at,expires_at) "
                    "VALUES (:invocation,:actor,:revision,:tool,:role,CAST(:scope AS jsonb),:key,:fingerprint,"
                    "CAST(:input AS jsonb),:status,CAST(:output AS jsonb),CAST(:error AS jsonb),:output_fingerprint,"
                    ":provenance,:correlation,:causation,:started,:finished,:expires)"
                ),
                {
                    "invocation": invocation.invocation_id,
                    "actor": invocation.actor_id,
                    "revision": tool_revision_id,
                    "tool": invocation.tool_name,
                    "role": invocation.actor_role,
                    "scope": _json(scope),
                    "key": invocation.idempotency_key,
                    "fingerprint": fingerprint,
                    "input": _json(invocation.input),
                    "status": result.status.value,
                    "output": None if result.output is None else _json(result.output),
                    "error": None if error_payload is None else _json(error_payload),
                    "output_fingerprint": result.output_fingerprint,
                    "provenance": result.provenance_id,
                    "correlation": invocation.correlation_id,
                    "causation": invocation.causation_id,
                    "started": result.started_at,
                    "finished": result.finished_at,
                    "expires": result.finished_at + timedelta(days=30),
                },
            )
            if result.status is ToolInvocationStatus.SUCCEEDED and definition.mutating:
                await self._persist_artifact(session, invocation, result)
            return result

    async def _claim_next_job(self) -> dict[str, object] | None:
        async with self._sessions() as session, session.begin():
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT j.job_id,j.requested_by_actor_id FROM platform.jobs j "
                            "WHERE j.job_type='generation' AND j.status IN ('requested','running') "
                            "AND NOT EXISTS (SELECT 1 FROM generation.generation_attempts a "
                            "WHERE a.job_id=j.job_id) ORDER BY j.requested_at,j.job_id "
                            "FOR UPDATE OF j SKIP LOCKED LIMIT 1"
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            actor_id = _uuid(row["requested_by_actor_id"])
            await self._set_actor(session, actor_id)
            generation = (
                (
                    await session.execute(
                        text(
                            "SELECT j.job_id,g.* FROM platform.jobs j "
                            "JOIN generation.generation_jobs g ON g.job_id=j.job_id "
                            "WHERE j.job_id=:job"
                        ),
                        {"job": row["job_id"]},
                    )
                )
                .mappings()
                .one()
            )
            await session.execute(
                text(
                    "UPDATE platform.jobs SET status='running',started_at=COALESCE(started_at,:now),"
                    "version=CASE WHEN status='running' THEN version ELSE version+1 END "
                    "WHERE job_id=:job"
                ),
                {"job": row["job_id"], "now": self._clock.now()},
            )
            return dict(generation)

    async def _actor_role(self, actor_id: UUID, tool_name: str) -> str:
        definition = TOOL_REGISTRY[tool_name]
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            granted = {
                str(value)
                for value in (
                    await session.scalars(
                        text(
                            "SELECT role FROM identity.account_roles "
                            "WHERE account_id=:actor AND revoked_at IS NULL"
                        ),
                        {"actor": actor_id},
                    )
                ).all()
            }
        granted.add("learner")
        for role in ("author", "reviewer", "worker", "learner", "support", "admin"):
            if role in granted and role in definition.roles:
                return role
        raise DomainError(ErrorCode.TOOL_NOT_ALLOWED)

    async def _finish_generation_job(
        self,
        claimed: dict[str, object],
        *,
        started_at: datetime,
        artifact_id: UUID | None,
        error_code: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> GenerationJobView:
        job_id = _uuid(claimed["job_id"])
        actor_id = _uuid(claimed["owner_account_id"])
        finished_at = self._clock.now()
        status = "succeeded" if error_code is None and artifact_id is not None else "failed"
        if status == "failed" and error_code is None:
            error_code = ErrorCode.TOOL_SCHEMA_INVALID.value
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            await session.execute(
                text(
                    "INSERT INTO generation.generation_attempts "
                    "(generation_attempt_id,job_id,owner_account_id,attempt_no,provider_code,"
                    "model_code,prompt_revision,tool_versions,input_fingerprint,status,error_code,"
                    "input_tokens,output_tokens,cost_micros,started_at,finished_at) VALUES "
                    "(:attempt,:job,:owner,1,:provider,:model,:prompt,:tools,:fingerprint,:status,"
                    ":error,:input_tokens,:output_tokens,0,:started,:finished)"
                ),
                {
                    "attempt": self._ids.new(),
                    "job": job_id,
                    "owner": actor_id,
                    "provider": claimed["provider_code"],
                    "model": claimed["model_code"],
                    "prompt": claimed["prompt_revision"],
                    "tools": claimed["tool_allowlist"],
                    "fingerprint": canonical_json_fingerprint(
                        {
                            "task_input": cast(dict[str, JsonValue], claimed["task_input"]),
                            "prompt_revision": str(claimed["prompt_revision"]),
                        }
                    ),
                    "status": status,
                    "error": error_code,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "started": started_at,
                    "finished": finished_at,
                },
            )
            await session.execute(
                text(
                    "UPDATE generation.generation_jobs SET result_draft_id=:artifact "
                    "WHERE job_id=:job"
                ),
                {"artifact": artifact_id, "job": job_id},
            )
            await session.execute(
                text(
                    "UPDATE platform.jobs SET status=:status,finished_at=:finished,"
                    "progress_completed=1,result_ref=:artifact,error_code=:error,version=version+1 "
                    "WHERE job_id=:job"
                ),
                {
                    "status": status,
                    "finished": finished_at,
                    "artifact": artifact_id,
                    "error": error_code,
                    "job": job_id,
                },
            )
            return await self._read_job(session, job_id)

    @staticmethod
    def _artifact_id(output: dict[str, JsonValue]) -> UUID | None:
        for key in ("draft_id", "validation_report_id", "quality_report_id"):
            value = output.get(key)
            if isinstance(value, str):
                return UUID(value)
        return None

    async def list_artifacts(
        self, actor_id: UUID, *, limit: int = 100
    ) -> tuple[AuthoringArtifactView, ...]:
        if not 1 <= limit <= 200:
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            rows = (
                await session.execute(
                    text(
                        "SELECT a.*,i.provenance_id FROM generation.authoring_artifacts a "
                        "JOIN generation.tool_invocations i ON i.invocation_id=a.source_invocation_id "
                        "ORDER BY a.created_at DESC,a.artifact_id DESC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
            ).mappings()
            return tuple(self._artifact_view(row) for row in rows)

    async def get_artifact(self, actor_id: UUID, artifact_id: UUID) -> AuthoringArtifactView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT a.*,i.provenance_id FROM generation.authoring_artifacts a "
                            "JOIN generation.tool_invocations i ON i.invocation_id=a.source_invocation_id "
                            "WHERE a.artifact_id=:artifact"
                        ),
                        {"artifact": artifact_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return self._artifact_view(row)

    async def _read_job(self, session: AsyncSession, job_id: UUID) -> GenerationJobView:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT j.*,g.task_type,g.provider_code,g.model_code,g.prompt_revision,"
                        "g.tool_allowlist,g.max_attempts,g.result_draft_id,"
                        "(SELECT count(*) FROM generation.generation_attempts a WHERE a.job_id=j.job_id) attempt_count "
                        "FROM platform.jobs j JOIN generation.generation_jobs g ON g.job_id=j.job_id "
                        "WHERE j.job_id=:job"
                    ),
                    {"job": job_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        return GenerationJobView(
            _uuid(row["job_id"]),
            _uuid(row["requested_by_actor_id"]),
            str(row["task_type"]),
            str(row["status"]),
            str(row["provider_code"]),
            str(row["model_code"]),
            str(row["prompt_revision"]),
            tuple(row["tool_allowlist"]),
            int(row["max_attempts"]),
            int(row["attempt_count"]),
            None if row["result_draft_id"] is None else _uuid(row["result_draft_id"]),
            cast(str | None, row["error_code"]),
            cast(datetime, row["requested_at"]),
            cast(datetime | None, row["started_at"]),
            cast(datetime | None, row["finished_at"]),
            int(row["version"]),
        )

    async def _persist_artifact(
        self, session: AsyncSession, invocation: ToolInvocation, result: ToolResult
    ) -> None:
        assert result.output is not None
        identifiers = (
            result.output.get("draft_id"),
            result.output.get("validation_report_id"),
            result.output.get("quality_report_id"),
        )
        raw_id = next((value for value in identifiers if isinstance(value, str)), None)
        if raw_id is None:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID)
        artifact_id = UUID(raw_id)
        artifact_type = cast(
            str,
            result.output.get("draft_type")
            or (
                "validation_report" if "validation_report_id" in result.output else "quality_report"
            ),
        )
        status = cast(
            str,
            result.output.get("status") or result.output.get("decision") or "draft",
        )
        checksum = cast(str, result.output.get("checksum") or result.output_fingerprint)
        artifact_payload: dict[str, JsonValue] = {
            "draft_payload": invocation.input,
            "tool_result": result.output,
        }
        await session.execute(
            text(
                "INSERT INTO generation.authoring_artifacts "
                "(artifact_id,owner_account_id,source_invocation_id,source_tool_name,artifact_type,"
                "status,payload,checksum,created_at) VALUES "
                "(:artifact,:owner,:invocation,:tool,:type,:status,CAST(:payload AS jsonb),:checksum,:now)"
            ),
            {
                "artifact": artifact_id,
                "owner": invocation.actor_id,
                "invocation": invocation.invocation_id,
                "tool": invocation.tool_name,
                "type": artifact_type,
                "status": status,
                "payload": _json(artifact_payload),
                "checksum": checksum,
                "now": result.finished_at,
            },
        )

    @staticmethod
    def _stored_tool_result(row: object) -> ToolResult:
        item = cast(dict[str, object], row)
        error_payload = cast(dict[str, JsonValue] | None, item["error_payload"])
        failure = None
        if error_payload is not None:
            details = error_payload.get("details_codes", [])
            failure = ToolFailure(
                str(error_payload["code"]),
                bool(error_payload.get("retryable", False)),
                cast(str | None, error_payload.get("field_path")),
                tuple(str(value) for value in details) if isinstance(details, list) else (),
            )
        return ToolResult(
            _uuid(item["invocation_id"]),
            "1.0.0",
            ToolInvocationStatus(str(item["status"])),
            cast(dict[str, JsonValue] | None, item["output_payload"]),
            failure,
            1,
            _uuid(item["provenance_id"]),
            cast(datetime, item["started_at"]),
            cast(datetime, item["finished_at"]),
            str(item["output_fingerprint"]),
        )

    @staticmethod
    def _artifact_view(row: object) -> AuthoringArtifactView:
        item = cast(dict[str, object], row)
        return AuthoringArtifactView(
            _uuid(item["artifact_id"]),
            str(item["artifact_type"]),
            str(item["source_tool_name"]),
            _uuid(item["provenance_id"]),
            str(item["status"]),
            cast(dict[str, JsonValue], item["payload"]),
            str(item["checksum"]),
            cast(datetime, item["created_at"]),
        )

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"), {"actor": str(actor_id)}
        )
