"""Authenticated W06 Word Bank and personal lexicon routes."""

# ruff: noqa: E501

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, Security
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.interfaces.http.routes.identity import (
    IDENTITY_PROBLEM_RESPONSES,
    SESSION_COOKIE,
    _context,
    _expected_version,
    _require_origin,
    _session_token,
)
from polyglot.modules.identity.application import (
    RECENT_AUTHENTICATION,
    CurrentSessionResult,
    IdentityApplicationService,
)
from polyglot.modules.identity.persistence import auth_sessions
from polyglot.modules.lexicon.core.queries import (
    GraphEdge,
    WordBankItem,
    bounded_neighborhood,
    paginate_word_bank,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.records import CommandReceipt, DomainEvent
from polyglot.platform.persistence.repositories import (
    SqlCommandReceiptStore,
    SqlEventOutboxRepository,
)

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
OriginHeader = Annotated[str, Header(alias="Origin")]
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str, Header(alias="If-Match")]
SessionCookieToken = Annotated[
    str | None,
    Security(APIKeyCookie(name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False)),
]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommandPayload(ClosedModel):
    data: dict[str, Any] = Field(default_factory=dict)


class MutationResponse(ClosedModel):
    resource_id: UUID
    version: int
    event_type: str


class WordBankItemResponse(ClosedModel):
    sense_id: UUID
    label: str
    encounter_count: int
    first_encountered_at: str | None
    last_encountered_at: str | None
    analysis_state: str
    familiarity_declaration: str | None
    learning_preference: str
    reasons: tuple[str, ...]


class UnresolvedMentionResponse(ClosedModel):
    mention_id: UUID
    encounter_id: UUID
    exact_surface: str
    created_at: str


class WordBankOverviewResponse(ClosedModel):
    items: tuple[WordBankItemResponse, ...]
    next_cursor: str | None
    encountered_sense_count: int
    unresolved_mention_count: int
    reference_set_code: str | None
    reference_revision: str | None
    reference_coverage_count: int | None
    reference_total_count: int | None
    unresolved_mentions: tuple[UnresolvedMentionResponse, ...] = ()


class LexicalAnnotationResponse(ClosedModel):
    annotation_id: UUID
    sense_id: UUID
    body: str
    version: int


class LexicalAnnotationPageResponse(ClosedModel):
    items: tuple[LexicalAnnotationResponse, ...]
    next_cursor: str | None


class SenseNeighborhoodResponse(ClosedModel):
    sense_id: UUID
    label: str
    definition: str
    nodes: tuple[UUID, ...]
    edges: tuple[dict[str, str], ...]
    truncated: bool
    version: int


@dataclass(frozen=True, slots=True)
class MutationResult:
    resource_id: UUID
    version: int
    event_type: str


class WordBankService(Protocol):
    async def execute(
        self,
        *,
        command_name: str,
        account_id: UUID,
        resource_id: UUID,
        payload: dict[str, Any],
        idempotency_key: str,
        expected_version: int | None,
        profile_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> MutationResult: ...

    async def get_sense(
        self,
        *,
        account_id: UUID,
        profile_id: UUID,
        sense_id: UUID,
        depth: int,
        edge_types: tuple[str, ...],
        max_nodes: int,
    ) -> SenseNeighborhoodResponse: ...

    async def get_word_bank(
        self,
        *,
        account_id: UUID,
        profile_id: UUID,
        limit: int,
        cursor: str | None,
        reference_set_code: str | None,
    ) -> WordBankOverviewResponse: ...

    async def list_annotations(
        self,
        *,
        account_id: UUID,
        profile_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> LexicalAnnotationPageResponse: ...


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    **IDENTITY_PROBLEM_RESPONSES,
    428: IDENTITY_PROBLEM_RESPONSES[422],
}
ETAG_RESPONSE = {
    **PROBLEM_RESPONSES,
    200: {
        "headers": {
            "ETag": {
                "description": "Quoted optimistic concurrency version.",
                "schema": {"type": "string"},
            }
        }
    },
}


def _required_version(value: str | None) -> int:
    if value is None:
        raise HTTPException(status_code=428, detail="If-Match is required")
    return _expected_version(value)


def word_bank_router(
    service: WordBankService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> WordBankService:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    async def session_for(
        request: Request,
        session_token: str | None,
        csrf_token: str | None = None,
        origin: str | None = None,
    ) -> CurrentSessionResult:
        if identity_service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        if origin is not None:
            _require_origin(origin, allowed_origin)
        current = await identity_service.get_current_session(
            _session_token(session_token), _context(request)
        )
        if csrf_token is not None and csrf_token != current.csrf_token:
            raise DomainError(ErrorCode.FORBIDDEN)
        return current

    async def account_for(
        request: Request,
        session_token: str | None,
        csrf_token: str | None = None,
        origin: str | None = None,
    ) -> UUID:
        return (await session_for(request, session_token, csrf_token, origin)).account_id

    def mutation_route(
        method: str,
        path: str,
        operation_id: str,
        command_name: str,
        event_type: str,
        *,
        versioned: bool = False,
    ) -> None:
        async def execute_mutation(
            request: Request,
            response: Response,
            idempotency_key: str,
            origin: str,
            csrf_token: str,
            payload: CommandPayload | None,
            if_match: str | None,
            session_token: str | None,
        ) -> MutationResponse:
            current = await session_for(request, session_token, csrf_token, origin)
            expected_version = _required_version(if_match) if versioned else None
            raw_resource_id = (
                request.path_params.get("sense_id")
                or request.path_params.get("mention_id")
                or request.path_params.get("relation_id")
                or request.path_params.get("encounter_id")
                or request.path_params.get("attempt_id")
                or request.path_params.get("annotation_id")
                or request.path_params.get("profile_id")
            )
            if raw_resource_id is None:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            result = await application_service().execute(
                command_name=command_name,
                account_id=current.account_id,
                resource_id=UUID(str(raw_resource_id)),
                payload={} if payload is None else payload.data,
                idempotency_key=idempotency_key,
                expected_version=expected_version,
                profile_id=(
                    UUID(str(request.path_params["profile_id"]))
                    if "profile_id" in request.path_params
                    else None
                ),
                session_id=current.session_id,
            )
            response.headers["ETag"] = f'"{result.version}"'
            return MutationResponse(
                resource_id=result.resource_id,
                version=result.version,
                event_type=event_type,
            )

        if versioned:
            async def versioned_endpoint(
                request: Request,
                response: Response,
                idempotency_key: IdempotencyKey,
                origin: OriginHeader,
                csrf_token: CsrfHeader,
                if_match: IfMatchHeader,
                payload: CommandPayload | None = None,
                session_token: SessionCookieToken = None,
            ) -> MutationResponse:
                return await execute_mutation(
                    request,
                    response,
                    idempotency_key,
                    origin,
                    csrf_token,
                    payload,
                    if_match,
                    session_token,
                )
            endpoint: Callable[..., Awaitable[MutationResponse]] = versioned_endpoint
        else:
            async def unversioned_endpoint(
                request: Request,
                response: Response,
                idempotency_key: IdempotencyKey,
                origin: OriginHeader,
                csrf_token: CsrfHeader,
                payload: CommandPayload | None = None,
                session_token: SessionCookieToken = None,
            ) -> MutationResponse:
                return await execute_mutation(
                    request,
                    response,
                    idempotency_key,
                    origin,
                    csrf_token,
                    payload,
                    None,
                    session_token,
                )
            endpoint = unversioned_endpoint

        endpoint.__name__ = operation_id
        router.add_api_route(
            path,
            endpoint,
            methods=[method],
            operation_id=operation_id,
            response_model=MutationResponse,
            responses=ETAG_RESPONSE if versioned else PROBLEM_RESPONSES,
        )

    command_specs = (
        ("POST", "/api/v1/language-profiles/{profile_id}/encounters", "record_lexical_encounter", "RecordLexicalEncounter", "lexical_encounter_recorded", False),
        ("POST", "/api/v1/lexical-mentions/{mention_id}:resolve", "resolve_mention", "ResolveMention", "mention_resolved", False),
        ("POST", "/api/v1/language-profiles/{profile_id}/private-lexicon", "add_private_lexical_unit", "AddPrivateLexicalUnit", "private_lexical_unit_added", False),
        ("POST", "/api/v1/lexical-senses/{sense_id}/personal-relations", "assert_lexical_relation", "AssertLexicalRelation", "lexical_relation_asserted", False),
        ("POST", "/api/v1/personal-lexical-relations/{relation_id}:retract", "retract_lexical_relation", "RetractLexicalRelation", "lexical_relation_retracted", False),
        ("POST", "/api/v1/language-profiles/{profile_id}/private-lexicon:merge", "merge_lexical_units", "MergeLexicalUnits", "lexical_units_merged", False),
        ("POST", "/api/v1/lexical-senses/{sense_id}:split-private", "split_lexical_sense", "SplitLexicalSense", "lexical_sense_split", False),
        ("DELETE", "/api/v1/lexical-encounters/{encounter_id}/private-context", "delete_private_context", "DeletePrivateContext", "private_context_deleted", False),
        ("POST", "/api/v1/attempts/{attempt_id}/lexical-gaps", "capture_lexical_gap", "CaptureLexicalGap", "lexical_gap_captured", False),
        ("PUT", "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/declaration", "declare_lexical_familiarity", "DeclareLexicalFamiliarity", "lexical_familiarity_declared", False),
        ("PUT", "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/preference", "set_lexical_learning_preference", "SetLexicalLearningPreference", "lexical_learning_preference_set", True),
        ("PUT", "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/annotation", "upsert_lexical_annotation", "UpsertLexicalAnnotation", "lexical_annotation_upserted", True),
        ("DELETE", "/api/v1/lexical-annotations/{annotation_id}", "delete_lexical_annotation", "DeleteLexicalAnnotation", "lexical_annotation_deleted", True),
    )
    for spec in command_specs:
        mutation_route(*spec[:5], versioned=bool(spec[5]))

    @router.get(
        "/api/v1/lexical-senses/{sense_id}",
        operation_id="get_lexical_sense",
        response_model=SenseNeighborhoodResponse,
        responses=ETAG_RESPONSE,
    )
    async def get_lexical_sense(
        sense_id: UUID,
        request: Request,
        response: Response,
        profile_id: Annotated[UUID, Query()],
        edge_types: Annotated[list[str], Query(min_length=1)],
        depth: Annotated[int, Query(ge=1, le=2)] = 1,
        max_nodes: Annotated[int, Query(ge=1, le=500)] = 100,
        session_token: SessionCookieToken = None,
    ) -> SenseNeighborhoodResponse:
        account_id = await account_for(request, session_token)
        result = await application_service().get_sense(
            account_id=account_id,
            profile_id=profile_id,
            sense_id=sense_id,
            depth=depth,
            edge_types=tuple(edge_types),
            max_nodes=max_nodes,
        )
        response.headers["ETag"] = f'"{result.version}"'
        return result

    @router.get(
        "/api/v1/language-profiles/{profile_id}/word-bank",
        operation_id="get_word_bank_overview",
        response_model=WordBankOverviewResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_word_bank_overview(
        profile_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
        reference_set_code: Annotated[str | None, Query(max_length=120)] = None,
        session_token: SessionCookieToken = None,
    ) -> WordBankOverviewResponse:
        account_id = await account_for(request, session_token)
        return await application_service().get_word_bank(
            account_id=account_id,
            profile_id=profile_id,
            limit=limit,
            cursor=cursor,
            reference_set_code=reference_set_code,
        )

    @router.get(
        "/api/v1/language-profiles/{profile_id}/lexical-annotations",
        operation_id="list_lexical_annotations",
        response_model=LexicalAnnotationPageResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def list_lexical_annotations(
        profile_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
        session_token: SessionCookieToken = None,
    ) -> LexicalAnnotationPageResponse:
        account_id = await account_for(request, session_token)
        return await application_service().list_annotations(
            account_id=account_id,
            profile_id=profile_id,
            limit=limit,
            cursor=cursor,
        )

    return router


_EVENT_BY_COMMAND = {
    "RecordLexicalEncounter": "lexical_encounter_recorded",
    "ResolveMention": "mention_resolved",
    "AddPrivateLexicalUnit": "private_lexical_unit_added",
    "AssertLexicalRelation": "lexical_relation_asserted",
    "RetractLexicalRelation": "lexical_relation_retracted",
    "MergeLexicalUnits": "lexical_units_merged",
    "SplitLexicalSense": "lexical_sense_split",
    "DeletePrivateContext": "private_context_deleted",
    "CaptureLexicalGap": "lexical_gap_captured",
    "DeclareLexicalFamiliarity": "lexical_familiarity_declared",
    "SetLexicalLearningPreference": "lexical_learning_preference_set",
    "UpsertLexicalAnnotation": "lexical_annotation_upserted",
    "DeleteLexicalAnnotation": "lexical_annotation_deleted",
}


class RecentReauthenticationVerifier(Protocol):
    async def __call__(
        self,
        session: AsyncSession,
        account_id: UUID,
        session_id: UUID,
        now: datetime,
    ) -> bool: ...


class SqlRecentReauthenticationVerifier:
    async def __call__(
        self,
        session: AsyncSession,
        account_id: UUID,
        session_id: UUID,
        now: datetime,
    ) -> bool:
        authenticated_at = await session.scalar(
            select(auth_sessions.c.authenticated_at).where(
                auth_sessions.c.session_id == session_id,
                auth_sessions.c.account_id == account_id,
                auth_sessions.c.revoked_at.is_(None),
            )
        )
        return (
            authenticated_at is not None
            and timedelta(0) <= now - authenticated_at <= RECENT_AUTHENTICATION
        )


@dataclass(frozen=True, slots=True)
class AttemptAuthorization:
    attempt_allowed: bool
    support_language_allowed: bool


class AttemptLexicalGapAuthorizer(Protocol):
    async def __call__(
        self,
        session: AsyncSession,
        account_id: UUID,
        profile_id: UUID,
        attempt_id: UUID,
        support_language_tag: str,
    ) -> AttemptAuthorization: ...


class SqlAttemptLexicalGapAuthorizer:
    _ALLOWED_EVENTS = (
        "exercise_attempt_opened",
        "attempt_draft_saved",
        "exercise_hint_used",
        "exercise_attempt_corrected",
    )

    async def __call__(
        self,
        session: AsyncSession,
        account_id: UUID,
        profile_id: UUID,
        attempt_id: UUID,
        support_language_tag: str,
    ) -> AttemptAuthorization:
        latest_event = await session.scalar(
            text(
                "SELECT event_type FROM platform.domain_events "
                "WHERE aggregate_type='exercise_attempt' AND aggregate_id=:attempt "
                "AND actor_id=:account AND profile_id=:profile "
                "ORDER BY aggregate_version DESC,recorded_at DESC,event_id DESC LIMIT 1"
            ),
            {"attempt": attempt_id, "account": account_id, "profile": profile_id},
        )
        if latest_event not in self._ALLOWED_EVENTS:
            return AttemptAuthorization(False, False)
        support_allowed = await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM catalogue.language_varieties variety "
                "JOIN language_profiles.support_language_authorizations authorization "
                "ON authorization.variety_id=variety.variety_id "
                "WHERE authorization.profile_id=:profile AND authorization.revoked_at IS NULL "
                "AND variety.language_tag=:language_tag)"
            ),
            {"profile": profile_id, "language_tag": support_language_tag},
        )
        return AttemptAuthorization(True, support_allowed is True)


class SqlWordBankService:
    """Transactional W06 adapter; it never writes mastery, debt, card, or list state."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        ids: IdGenerator | None = None,
        attempt_authorizer: AttemptLexicalGapAuthorizer | None = None,
        recent_reauth_verifier: RecentReauthenticationVerifier | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._ids = ids or Uuid7Generator()
        self._attempt_authorizer = attempt_authorizer or SqlAttemptLexicalGapAuthorizer()
        self._recent_reauth_verifier = (
            recent_reauth_verifier or SqlRecentReauthenticationVerifier()
        )

    async def _set_actor(self, session: AsyncSession, account_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id', :account_id, true)"),
            {"account_id": str(account_id)},
        )

    async def _assert_owner(
        self, session: AsyncSession, account_id: UUID, profile_id: UUID
    ) -> None:
        owned = await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles "
                "WHERE profile_id=:profile AND account_id=:account AND status <> 'deleted')"
            ),
            {"profile": profile_id, "account": account_id},
        )
        if owned is not True:
            raise DomainError(ErrorCode.NOT_FOUND)

    @staticmethod
    def _uuid(payload: dict[str, Any], name: str) -> UUID:
        try:
            return UUID(str(payload[name]))
        except (KeyError, TypeError, ValueError) as error:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{name} is required") from error

    async def _profile_for_command(
        self,
        session: AsyncSession,
        command_name: str,
        resource_id: UUID,
        payload: dict[str, Any],
        explicit_profile_id: UUID | None,
    ) -> UUID:
        if explicit_profile_id is not None:
            return explicit_profile_id
        if command_name in {
            "RecordLexicalEncounter",
            "AddPrivateLexicalUnit",
            "MergeLexicalUnits",
            "DeclareLexicalFamiliarity",
            "SetLexicalLearningPreference",
            "UpsertLexicalAnnotation",
        }:
            return resource_id
        table_and_column = {
            "ResolveMention": ("lexicon.lexical_mentions", "mention_id"),
            "RetractLexicalRelation": (
                "lexicon.personal_lexical_relations",
                "relation_id",
            ),
            "DeletePrivateContext": ("lexicon.lexical_encounters", "encounter_id"),
            "DeleteLexicalAnnotation": ("lexicon.lexical_annotations", "annotation_id"),
            "SplitLexicalSense": ("lexicon.private_lexical_senses", "sense_id"),
        }.get(command_name)
        if table_and_column is not None:
            table_name, column_name = table_and_column
            profile_id = await session.scalar(
                text(f"SELECT profile_id FROM {table_name} WHERE {column_name}=:id"),
                {"id": resource_id},
            )
            if profile_id is None:
                if command_name == "SplitLexicalSense":
                    raise DomainError(ErrorCode.CANONICAL_SENSE_IMMUTABLE)
                raise DomainError(ErrorCode.NOT_FOUND)
            return UUID(str(profile_id))
        return self._uuid(payload, "profile_id")

    async def execute(
        self,
        *,
        command_name: str,
        account_id: UUID,
        resource_id: UUID,
        payload: dict[str, Any],
        idempotency_key: str,
        expected_version: int | None,
        profile_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> MutationResult:
        if command_name not in _EVENT_BY_COMMAND:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        fingerprint_payload: dict[str, JsonValue] = {
            "command": command_name,
            "resource_id": str(resource_id),
            "payload": payload,
            "expected_version": expected_version,
            "profile_id": None if profile_id is None else str(profile_id),
        }
        fingerprint = canonical_json_fingerprint(fingerprint_payload)
        async with self._session_factory() as session:
            await self._set_actor(session, account_id)
            explicit_profile_id = profile_id
            profile_id = await self._profile_for_command(
                session, command_name, resource_id, payload, profile_id
            )
            await self._assert_owner(session, account_id, profile_id)
            now = datetime.now(UTC)
            if command_name == "DeletePrivateContext":
                if session_id is None or not await self._recent_reauth_verifier(
                    session, account_id, session_id, now
                ):
                    raise DomainError(ErrorCode.UNAUTHENTICATED)
            if command_name == "CaptureLexicalGap":
                support_language = str(payload.get("support_language_tag", ""))
                authorization = await self._attempt_authorizer(
                    session, account_id, profile_id, resource_id, support_language
                )
                if not authorization.attempt_allowed:
                    raise DomainError(ErrorCode.NOT_FOUND)
                if not authorization.support_language_allowed:
                    raise DomainError(ErrorCode.SUPPORT_LANGUAGE_NOT_ALLOWED)
            command_id = self._ids.new()
            reservation = await SqlCommandReceiptStore(session).reserve(
                CommandReceipt(
                    command_id=command_id,
                    command_type=command_name,
                    actor_id=account_id,
                    aggregate_type="language_profile",
                    aggregate_id=profile_id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                    expected_version=expected_version,
                    received_at=now,
                    result_ref=None,
                    result_payload=None,
                    status="started",
                    expires_at=now + timedelta(days=30),
                )
            )
            if not reservation.created:
                stored = reservation.receipt.result_payload
                if reservation.receipt.status != "succeeded" or stored is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return MutationResult(
                    UUID(str(stored["resource_id"])),
                    int(stored["version"]),
                    _EVENT_BY_COMMAND[command_name],
                )

            result_id, version = await self._apply_command(
                session,
                command_name=command_name,
                profile_id=profile_id,
                resource_id=resource_id,
                payload=payload,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                resource_is_path_target=explicit_profile_id is not None,
            )
            result_payload: dict[str, JsonValue] = {
                "resource_id": str(result_id),
                "version": version,
            }
            await SqlCommandReceiptStore(session).complete(
                command_id=command_id,
                status="succeeded",
                result_ref=result_id,
                result_payload=result_payload,
            )
            recorded_at = datetime.now(UTC)
            await SqlEventOutboxRepository(session, self._ids).add(
                DomainEvent(
                    event_id=self._ids.new(),
                    event_type=_EVENT_BY_COMMAND[command_name],
                    schema_version=1,
                    aggregate_type="lexicon_resource",
                    aggregate_id=result_id,
                    aggregate_version=version,
                    actor_type="account",
                    actor_id=account_id,
                    profile_id=profile_id,
                    occurred_at=recorded_at,
                    recorded_at=recorded_at,
                    correlation_id=self._ids.new(),
                    causation_id=None,
                    command_id=command_id,
                    privacy_class="personal",
                    policy_versions={"lexicon": "w06-v1"},
                    payload={"resource_id": str(result_id), "version": version},
                    expires_at=recorded_at + timedelta(days=3650),
                    subject_type="profile",
                    subject_id=profile_id,
                ),
                destinations=("learning.projections",),
            )
            await session.commit()
            return MutationResult(result_id, version, _EVENT_BY_COMMAND[command_name])

    async def _apply_command(
        self,
        session: AsyncSession,
        *,
        command_name: str,
        profile_id: UUID,
        resource_id: UUID,
        payload: dict[str, Any],
        expected_version: int | None,
        idempotency_key: str,
        fingerprint: str,
        resource_is_path_target: bool,
    ) -> tuple[UUID, int]:
        now = datetime.now(UTC)
        if command_name == "RecordLexicalEncounter":
            encounter_id = self._uuid(payload, "encounter_id")
            mention_id = self._uuid(payload, "mention_id")
            occurred_at = datetime.fromisoformat(str(payload.get("occurred_at", now.isoformat())))
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_encounters "
                    "(encounter_id,profile_id,exact_surface,source_type,source_ref,"
                    "source_revision_ref,modality,lexical_role,operation,help_state,result_state,"
                    "correction_ref,correction_confidence,context_private,context_fingerprint,"
                    "context_retention,occurred_at,idempotency_key,request_fingerprint) VALUES "
                    "(:id,:profile,:surface,:source_type,:source_ref,:source_revision,:modality,"
                    ":role,:operation,:help,:result,:correction,:confidence,:context,:context_fp,"
                    ":retention,:occurred,:key,:fingerprint)"
                ),
                {
                    "id": encounter_id,
                    "profile": profile_id,
                    "surface": str(payload.get("exact_surface", "")),
                    "source_type": str(payload.get("source_type", "manual")),
                    "source_ref": str(payload.get("source_ref", "manual")),
                    "source_revision": str(payload.get("source_revision_ref", "")),
                    "modality": str(payload.get("modality", "reading")),
                    "role": str(payload.get("lexical_role", "stimulus")),
                    "operation": str(payload.get("operation", "seen")),
                    "help": str(payload.get("help_state", "none")),
                    "result": str(payload.get("result_state", "not_evaluable")),
                    "correction": str(payload.get("correction_ref", "none")),
                    "confidence": float(payload.get("correction_confidence", 0.0)),
                    "context": payload.get("context_private"),
                    "context_fp": str(payload.get("context_fingerprint", "")),
                    "retention": str(payload.get("context_retention", "minimal")),
                    "occurred": occurred_at,
                    "key": idempotency_key,
                    "fingerprint": fingerprint,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_mentions "
                    "(mention_id,profile_id,encounter_id,exact_surface,form_analysis_id,"
                    "analysis_revision_ref,ordinal,created_at) VALUES "
                    "(:mention,:profile,:encounter,:surface,:form,:revision,1,:created)"
                ),
                {
                    "mention": mention_id,
                    "profile": profile_id,
                    "encounter": encounter_id,
                    "surface": str(payload.get("exact_surface", "")),
                    "form": UUID(str(payload["form_analysis_id"]))
                    if payload.get("form_analysis_id")
                    else None,
                    "revision": str(payload.get("analysis_revision_ref", "manual-v1")),
                    "created": occurred_at,
                },
            )
            for raw_candidate in payload.get("candidates", []):
                if not isinstance(raw_candidate, dict):
                    raise DomainError(ErrorCode.VALIDATION_FAILED)
                await session.execute(
                    text(
                        "INSERT INTO lexicon.mention_candidates "
                        "(candidate_id,profile_id,mention_id,sense_id,sense_scope,confidence,"
                        "source,created_at) VALUES "
                        "(:candidate,:profile,:mention,:sense,:scope,:confidence,:source,:created)"
                    ),
                    {
                        "candidate": self._uuid(raw_candidate, "candidate_id"),
                        "profile": profile_id,
                        "mention": mention_id,
                        "sense": self._uuid(raw_candidate, "sense_id"),
                        "scope": str(raw_candidate.get("sense_scope", "shared")),
                        "confidence": float(raw_candidate.get("confidence", 0.0)),
                        "source": str(raw_candidate.get("source", "unknown")),
                        "created": occurred_at,
                    },
                )
            return encounter_id, 1
        if command_name == "ResolveMention":
            candidate_id = self._uuid(payload, "candidate_id")
            candidate = (
                await session.execute(
                    text(
                        "SELECT sense_id FROM lexicon.mention_candidates "
                        "WHERE profile_id=:profile AND mention_id=:mention AND candidate_id=:candidate"
                    ),
                    {"profile": profile_id, "mention": resource_id, "candidate": candidate_id},
                )
            ).one_or_none()
            if candidate is None:
                raise DomainError(ErrorCode.SENSE_AMBIGUOUS)
            result_id = self._uuid(payload, "resolution_id") if "resolution_id" in payload else self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO lexicon.mention_resolutions "
                    "(resolution_id,profile_id,mention_id,candidate_id,sense_id,resolver_type,"
                    "confidence,supersedes_resolution_id,created_at,idempotency_key,request_fingerprint) "
                    "VALUES (:id,:profile,:mention,:candidate,:sense,'user',1,NULL,:now,:key,:fp)"
                ),
                {"id": result_id, "profile": profile_id, "mention": resource_id, "candidate": candidate_id, "sense": candidate.sense_id, "now": now, "key": idempotency_key, "fp": fingerprint},
            )
            return result_id, 1
        if command_name == "AddPrivateLexicalUnit":
            result_id = self._uuid(payload, "lexical_unit_id") if "lexical_unit_id" in payload else self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO lexicon.private_lexical_units "
                    "(lexical_unit_id,profile_id,variety_id,unit_type,lemma,normalization_key,"
                    "components,provenance_ref,version,created_at) VALUES "
                    "(:id,:profile,:variety,:type,:lemma,lower(:lemma),:components,'user',1,:now)"
                ),
                {"id": result_id, "profile": profile_id, "variety": self._uuid(payload, "variety_id"), "type": str(payload.get("unit_type", "word")), "lemma": str(payload.get("lemma", "")), "components": [UUID(str(item)) for item in payload.get("components", [])], "now": now},
            )
            return result_id, 1
        if command_name == "AssertLexicalRelation":
            result_id = self._uuid(payload, "relation_id") if "relation_id" in payload else self._ids.new()
            target_sense_id = self._uuid(payload, "target_sense_id")
            await self._assert_sense_visible(session, profile_id, resource_id)
            await self._assert_sense_visible(session, profile_id, target_sense_id)
            await session.execute(
                text(
                    "INSERT INTO lexicon.personal_lexical_relations "
                    "(relation_id,profile_id,source_sense_id,target_sense_id,relation_type,"
                    "direction,provenance_ref,confidence,created_at,version) VALUES "
                    "(:id,:profile,:source,:target,:type,:direction,'user',:confidence,:now,1)"
                ),
                {"id": result_id, "profile": profile_id, "source": resource_id, "target": target_sense_id, "type": str(payload.get("relation_type", "association")), "direction": str(payload.get("direction", "directed")), "confidence": float(payload.get("confidence", 1.0)), "now": now},
            )
            return result_id, 1
        if command_name == "RetractLexicalRelation":
            result_id = self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_relation_retractions "
                    "(retraction_id,profile_id,relation_id,reason,retracted_at,idempotency_key,"
                    "request_fingerprint) VALUES (:id,:profile,:relation,:reason,:now,:key,:fp)"
                ),
                {"id": result_id, "profile": profile_id, "relation": resource_id, "reason": str(payload.get("reason", "user_request")), "now": now, "key": idempotency_key, "fp": fingerprint},
            )
            return resource_id, 1
        if command_name == "MergeLexicalUnits":
            unit_ids = tuple(UUID(str(value)) for value in payload.get("unit_ids", ()))
            target_id = self._uuid(payload, "target_unit_id")
            if target_id not in unit_ids or len(unit_ids) < 2:
                raise DomainError(ErrorCode.MERGE_AMBIGUOUS)
            updated = await session.execute(
                text(
                    "UPDATE lexicon.private_lexical_units SET merged_into_unit_id=:target,"
                    "version=version+1 WHERE profile_id=:profile AND lexical_unit_id=ANY(:units) "
                    "AND lexical_unit_id<>:target AND merged_into_unit_id IS NULL"
                ),
                {"target": target_id, "profile": profile_id, "units": list(unit_ids)},
            )
            if getattr(updated, "rowcount", 0) != len(unit_ids) - 1:
                raise DomainError(ErrorCode.MERGE_AMBIGUOUS)
            return target_id, 1
        if command_name == "SplitLexicalSense":
            new_sense_id = (
                self._uuid(payload, "new_sense_id")
                if "new_sense_id" in payload
                else self._ids.new()
            )
            source = (
                await session.execute(
                    text(
                        "SELECT lexical_unit_id FROM lexicon.private_lexical_senses "
                        "WHERE profile_id=:profile AND sense_id=:sense"
                    ),
                    {"profile": profile_id, "sense": resource_id},
                )
            ).one_or_none()
            if source is None:
                raise DomainError(ErrorCode.CANONICAL_SENSE_IMMUTABLE)
            await session.execute(
                text(
                    "INSERT INTO lexicon.private_lexical_senses "
                    "(sense_id,profile_id,lexical_unit_id,sense_code,definition,"
                    "support_language_tag,provenance_ref,split_from_sense_id,created_at) VALUES "
                    "(:id,:profile,:unit,:code,:definition,:language,'user',:source,:now)"
                ),
                {
                    "id": new_sense_id,
                    "profile": profile_id,
                    "unit": source.lexical_unit_id,
                    "code": str(payload.get("sense_code", "private.split")),
                    "definition": str(payload.get("definition", "")),
                    "language": payload.get("support_language_tag"),
                    "source": resource_id,
                    "now": now,
                },
            )
            return new_sense_id, 1
        if command_name == "DeletePrivateContext":
            updated = await session.execute(
                text(
                    "UPDATE lexicon.lexical_encounters SET context_private=NULL,context_deleted_at=:now "
                    "WHERE encounter_id=:id AND profile_id=:profile AND context_deleted_at IS NULL"
                ),
                {"now": now, "id": resource_id, "profile": profile_id},
            )
            if not getattr(updated, "rowcount", 0):
                raise DomainError(ErrorCode.NOT_FOUND)
            return resource_id, 1
        if command_name == "CaptureLexicalGap":
            encounter_id = (
                self._uuid(payload, "encounter_id")
                if "encounter_id" in payload
                else self._ids.new()
            )
            mention_id = (
                self._uuid(payload, "mention_id")
                if "mention_id" in payload
                else self._ids.new()
            )
            intention = str(payload.get("intended_support_text", "")).strip()
            if not intention:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            context = payload.get("minimal_context")
            context_text = None if context is None else str(context)
            context_fingerprint = canonical_json_fingerprint(context_text)
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_encounters "
                    "(encounter_id,profile_id,exact_surface,source_type,source_ref,"
                    "source_revision_ref,modality,lexical_role,operation,help_state,result_state,"
                    "correction_ref,correction_confidence,context_private,context_fingerprint,"
                    "context_retention,occurred_at,idempotency_key,request_fingerprint) VALUES "
                    "(:id,:profile,:surface,'attempt',:attempt,:revision,'writing','production',"
                    "'queried','self_reported','not_evaluable','none',0,:context,:context_fp,"
                    "'private_until_deleted',:now,:key,:fingerprint)"
                ),
                {
                    "id": encounter_id,
                    "profile": profile_id,
                    "surface": intention,
                    "attempt": str(resource_id),
                    "revision": "gap-v1:" + str(payload.get("support_language_tag", "")),
                    "context": context_text,
                    "context_fp": context_fingerprint,
                    "now": now,
                    "key": idempotency_key,
                    "fingerprint": fingerprint,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_mentions "
                    "(mention_id,profile_id,encounter_id,exact_surface,analysis_revision_ref,"
                    "ordinal,created_at) VALUES (:mention,:profile,:encounter,:surface,'gap-v1',1,:now)"
                ),
                {
                    "mention": mention_id,
                    "profile": profile_id,
                    "encounter": encounter_id,
                    "surface": intention,
                    "now": now,
                },
            )
            return encounter_id, 1
        if command_name == "DeclareLexicalFamiliarity":
            result_id = self._ids.new()
            sense_id = (
                resource_id
                if resource_is_path_target
                else self._uuid(payload, "sense_id")
            )
            await self._assert_sense_visible(session, profile_id, sense_id)
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_declarations "
                    "(declaration_id,profile_id,sense_id,familiarity,declared_at,"
                    "supersedes_declaration_id,idempotency_key,request_fingerprint) "
                    "VALUES (:id,:profile,:sense,:value,:now,NULL,:key,:fp)"
                ),
                {"id": result_id, "profile": profile_id, "sense": sense_id, "value": str(payload.get("familiarity", "seen")), "now": now, "key": idempotency_key, "fp": fingerprint},
            )
            return result_id, 1
        if command_name == "SetLexicalLearningPreference":
            sense_id = (
                resource_id
                if resource_is_path_target
                else self._uuid(payload, "sense_id")
            )
            await self._assert_sense_visible(session, profile_id, sense_id)
            current = await session.scalar(
                text("SELECT version FROM lexicon.lexical_preferences WHERE profile_id=:profile AND sense_id=:sense FOR UPDATE"),
                {"profile": profile_id, "sense": sense_id},
            )
            current_version = 0 if current is None else int(current)
            if expected_version != current_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            result_id = self._ids.new()
            version = current_version + 1
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_preferences "
                    "(preference_id,profile_id,sense_id,preference,version,set_at,idempotency_key,request_fingerprint) "
                    "VALUES (:id,:profile,:sense,:value,:version,:now,:key,:fp) "
                    "ON CONFLICT (profile_id,sense_id) DO UPDATE SET preference=EXCLUDED.preference,"
                    "version=EXCLUDED.version,set_at=EXCLUDED.set_at,idempotency_key=EXCLUDED.idempotency_key,"
                    "request_fingerprint=EXCLUDED.request_fingerprint"
                ),
                {"id": result_id, "profile": profile_id, "sense": sense_id, "value": str(payload.get("preference", "normal")), "version": version, "now": now, "key": idempotency_key, "fp": fingerprint},
            )
            return result_id, version
        if command_name == "UpsertLexicalAnnotation":
            adapted = (
                {**payload, "sense_id": str(resource_id)}
                if resource_is_path_target
                else payload
            )
            await self._assert_sense_visible(session, profile_id, self._uuid(adapted, "sense_id"))
            return await self._upsert_annotation(session, profile_id, adapted, expected_version, idempotency_key, fingerprint, now)
        if command_name == "DeleteLexicalAnnotation":
            current = await session.scalar(text("SELECT version FROM lexicon.lexical_annotations WHERE annotation_id=:id AND profile_id=:profile FOR UPDATE"), {"id": resource_id, "profile": profile_id})
            if current is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if expected_version != int(current):
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            version = int(current) + 1
            await session.execute(text("UPDATE lexicon.lexical_annotations SET version=:version,updated_at=:now,deleted_at=:now WHERE annotation_id=:id"), {"version": version, "now": now, "id": resource_id})
            return resource_id, version
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{command_name} payload adapter pending")

    async def _assert_sense_visible(
        self, session: AsyncSession, profile_id: UUID, sense_id: UUID
    ) -> None:
        visible = await session.scalar(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM catalogue.lexical_senses WHERE sense_id=:sense "
                "UNION ALL SELECT 1 FROM lexicon.private_lexical_senses "
                "WHERE sense_id=:sense AND profile_id=:profile)"
            ),
            {"sense": sense_id, "profile": profile_id},
        )
        if visible is not True:
            raise DomainError(ErrorCode.NOT_FOUND)

    async def _upsert_annotation(self, session: AsyncSession, profile_id: UUID, payload: dict[str, Any], expected_version: int | None, idempotency_key: str, fingerprint: str, now: datetime) -> tuple[UUID, int]:
        sense_id = self._uuid(payload, "sense_id")
        row = (
            await session.execute(text("SELECT annotation_id,version FROM lexicon.lexical_annotations WHERE profile_id=:profile AND sense_id=:sense FOR UPDATE"), {"profile": profile_id, "sense": sense_id})
        ).one_or_none()
        current_version = 0 if row is None else int(row.version)
        if expected_version != current_version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        annotation_id = self._ids.new() if row is None else UUID(str(row.annotation_id))
        version = current_version + 1
        if row is None:
            await session.execute(text("INSERT INTO lexicon.lexical_annotations (annotation_id,profile_id,sense_id,version,created_at,updated_at) VALUES (:id,:profile,:sense,:version,:now,:now)"), {"id": annotation_id, "profile": profile_id, "sense": sense_id, "version": version, "now": now})
        else:
            await session.execute(text("UPDATE lexicon.lexical_annotations SET version=:version,updated_at=:now,deleted_at=NULL WHERE annotation_id=:id"), {"version": version, "now": now, "id": annotation_id})
        await session.execute(text("INSERT INTO lexicon.lexical_annotation_revisions (annotation_revision_id,profile_id,annotation_id,version,body,created_at,idempotency_key,request_fingerprint) VALUES (:revision,:profile,:annotation,:version,:body,:now,:key,:fp)"), {"revision": self._ids.new(), "profile": profile_id, "annotation": annotation_id, "version": version, "body": str(payload.get("body", "")), "now": now, "key": idempotency_key, "fp": fingerprint})
        return annotation_id, version

    async def get_word_bank(self, *, account_id: UUID, profile_id: UUID, limit: int, cursor: str | None, reference_set_code: str | None) -> WordBankOverviewResponse:
        async with self._session_factory() as session:
            await self._set_actor(session, account_id)
            await self._assert_owner(session, account_id, profile_id)
            if reference_set_code is not None:
                reference = (
                    await session.execute(
                        text(
                            "SELECT reference_set_id,revision FROM lexicon.lexical_reference_sets "
                            "WHERE code=:code ORDER BY created_at DESC,reference_set_id DESC LIMIT 1"
                        ),
                        {"code": reference_set_code},
                    )
                ).one_or_none()
                if reference is None:
                    raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
                rows = (
                    await session.execute(
                        text(
                            "WITH latest AS (SELECT DISTINCT ON (mention_id) mention_id,sense_id "
                            "FROM lexicon.mention_resolutions WHERE profile_id=:profile "
                            "ORDER BY mention_id,created_at DESC,resolution_id DESC), observed AS ("
                            "SELECT latest.sense_id,count(*) AS encounters,min(e.occurred_at) AS first_at,"
                            "max(e.occurred_at) AS last_at FROM latest JOIN lexicon.lexical_mentions m "
                            "ON m.profile_id=:profile AND m.mention_id=latest.mention_id "
                            "JOIN lexicon.lexical_encounters e ON e.profile_id=:profile "
                            "AND e.encounter_id=m.encounter_id GROUP BY latest.sense_id) "
                            "SELECT entry.sense_id,entry.label,entry.ordinal,observed.encounters,"
                            "observed.first_at,observed.last_at,(SELECT familiarity FROM "
                            "lexicon.lexical_declarations declaration WHERE declaration.profile_id=:profile "
                            "AND declaration.sense_id=entry.sense_id ORDER BY declaration.declared_at DESC,"
                            "declaration.declaration_id DESC LIMIT 1) AS familiarity,(SELECT preference "
                            "FROM lexicon.lexical_preferences preference WHERE preference.profile_id=:profile "
                            "AND preference.sense_id=entry.sense_id) AS preference "
                            "FROM lexicon.lexical_reference_entries entry "
                            "LEFT JOIN observed ON observed.sense_id=entry.sense_id "
                            "WHERE entry.reference_set_id=:reference ORDER BY entry.ordinal,entry.sense_id"
                        ),
                        {"profile": profile_id, "reference": reference.reference_set_id},
                    )
                ).mappings().all()
                source = tuple(
                    WordBankItem(
                        UUID(str(row["sense_id"])),
                        str(row["label"]),
                        int(row["ordinal"]),
                        (f"reference:{reference_set_code}:{reference.revision}",),
                    )
                    for row in rows
                )
                page = paginate_word_bank(
                    source,
                    limit=limit,
                    cursor=cursor,
                    reference_revision=str(reference.revision),
                )
                by_id = {UUID(str(row["sense_id"])): row for row in rows}
                items = tuple(
                    WordBankItemResponse(
                        sense_id=item.sense_id,
                        label=item.label,
                        encounter_count=int(by_id[item.sense_id]["encounters"] or 0),
                        first_encountered_at=(
                            by_id[item.sense_id]["first_at"].isoformat()
                            if by_id[item.sense_id]["first_at"] is not None
                            else None
                        ),
                        last_encountered_at=(
                            by_id[item.sense_id]["last_at"].isoformat()
                            if by_id[item.sense_id]["last_at"] is not None
                            else None
                        ),
                        analysis_state=(
                            "resolved"
                            if by_id[item.sense_id]["encounters"] is not None
                            else "unobserved"
                        ),
                        familiarity_declaration=by_id[item.sense_id]["familiarity"],
                        learning_preference=str(
                            by_id[item.sense_id]["preference"] or "normal"
                        ),
                        reasons=(
                            ("encountered",)
                            if by_id[item.sense_id]["encounters"] is not None
                            else ("absence_of_evidence",)
                        ),
                    )
                    for item in page.items
                )
                coverage = sum(row["encounters"] is not None for row in rows)
                unresolved_mentions = await self._unresolved_mentions(session, profile_id)
                return WordBankOverviewResponse(
                    items=items,
                    next_cursor=page.next_cursor,
                    encountered_sense_count=coverage,
                    unresolved_mention_count=len(unresolved_mentions),
                    reference_set_code=reference_set_code,
                    reference_revision=str(reference.revision),
                    reference_coverage_count=coverage,
                    reference_total_count=len(rows),
                    unresolved_mentions=unresolved_mentions,
                )
            rows = (
                await session.execute(text("WITH latest AS (SELECT DISTINCT ON (mention_id) mention_id,sense_id FROM lexicon.mention_resolutions WHERE profile_id=:profile ORDER BY mention_id,created_at DESC,resolution_id DESC) SELECT latest.sense_id,min(e.exact_surface) AS label,count(*) AS encounters,min(e.occurred_at) AS first_at,max(e.occurred_at) AS last_at FROM latest JOIN lexicon.lexical_mentions m ON m.mention_id=latest.mention_id JOIN lexicon.lexical_encounters e ON e.encounter_id=m.encounter_id GROUP BY latest.sense_id ORDER BY min(e.exact_surface),latest.sense_id"), {"profile": profile_id})
            ).mappings().all()
            source = tuple(WordBankItem(UUID(str(row["sense_id"])), str(row["label"]), index, ("encounter",)) for index, row in enumerate(rows, 1))
            page = paginate_word_bank(source, limit=limit, cursor=cursor)
            by_id = {UUID(str(row["sense_id"])): row for row in rows}
            items = tuple(
                WordBankItemResponse(
                    sense_id=item.sense_id,
                    label=item.label,
                    encounter_count=int(by_id[item.sense_id]["encounters"]),
                    first_encountered_at=by_id[item.sense_id]["first_at"].isoformat(),
                    last_encountered_at=by_id[item.sense_id]["last_at"].isoformat(),
                    analysis_state="resolved",
                    familiarity_declaration=None,
                    learning_preference="normal",
                    reasons=("encountered",),
                )
                for item in page.items
            )
            unresolved_mentions = await self._unresolved_mentions(session, profile_id)
            return WordBankOverviewResponse(items=items, next_cursor=page.next_cursor, encountered_sense_count=len(rows), unresolved_mention_count=len(unresolved_mentions), reference_set_code=None, reference_revision=None, reference_coverage_count=None, reference_total_count=None, unresolved_mentions=unresolved_mentions)

    async def _unresolved_mentions(
        self, session: AsyncSession, profile_id: UUID
    ) -> tuple[UnresolvedMentionResponse, ...]:
        rows = (
            await session.execute(
                text(
                    "SELECT m.mention_id,m.encounter_id,m.exact_surface,m.created_at "
                    "FROM lexicon.lexical_mentions m WHERE m.profile_id=:profile "
                    "AND NOT EXISTS (SELECT 1 FROM lexicon.mention_resolutions r "
                    "WHERE r.profile_id=:profile AND r.mention_id=m.mention_id) "
                    "ORDER BY m.created_at,m.mention_id LIMIT 100"
                ),
                {"profile": profile_id},
            )
        ).mappings().all()
        return tuple(
            UnresolvedMentionResponse(
                mention_id=UUID(str(row["mention_id"])),
                encounter_id=UUID(str(row["encounter_id"])),
                exact_surface=str(row["exact_surface"]),
                created_at=row["created_at"].isoformat(),
            )
            for row in rows
        )

    async def get_sense(self, *, account_id: UUID, profile_id: UUID, sense_id: UUID, depth: int, edge_types: tuple[str, ...], max_nodes: int) -> SenseNeighborhoodResponse:
        async with self._session_factory() as session:
            await self._set_actor(session, account_id)
            await self._assert_owner(session, account_id, profile_id)
            row = (
                await session.execute(text("SELECT sense.sense_id,revision.definition,unit_revision.lemma FROM catalogue.lexical_senses sense JOIN catalogue.lexical_sense_revisions revision ON revision.sense_id=sense.sense_id JOIN catalogue.lexical_unit_revisions unit_revision ON unit_revision.lexical_unit_id=sense.lexical_unit_id WHERE sense.sense_id=:sense ORDER BY revision.revision_no DESC,unit_revision.revision_no DESC LIMIT 1"), {"sense": sense_id})
            ).mappings().one_or_none()
            if row is None:
                row = (
                    await session.execute(text("SELECT sense_id,definition,(SELECT lemma FROM lexicon.private_lexical_units unit WHERE unit.profile_id=:profile AND unit.lexical_unit_id=sense.lexical_unit_id) AS lemma FROM lexicon.private_lexical_senses sense WHERE profile_id=:profile AND sense_id=:sense"), {"profile": profile_id, "sense": sense_id})
                ).mappings().one_or_none()
            if row is None:
                row = (
                    await session.execute(
                        text(
                            "SELECT sense_id,definition,label AS lemma FROM "
                            "lexicon.lexical_reference_entries WHERE sense_id=:sense "
                            "ORDER BY reference_set_id LIMIT 1"
                        ),
                        {"sense": sense_id},
                    )
                ).mappings().one_or_none()
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            node_rows = (
                await session.execute(
                    text(
                        "WITH RECURSIVE walk(node,depth) AS (VALUES (CAST(:root AS uuid),0) "
                        "UNION SELECT relation.target_sense_id,walk.depth+1 FROM walk JOIN "
                        "lexicon.personal_lexical_relations relation ON relation.profile_id=:profile "
                        "AND relation.source_sense_id=walk.node AND relation.relation_type=ANY(:types) "
                        "AND NOT EXISTS (SELECT 1 FROM lexicon.lexical_relation_retractions retract "
                        "WHERE retract.profile_id=:profile AND retract.relation_id=relation.relation_id) "
                        "WHERE walk.depth<:depth) SELECT node,min(depth) AS depth FROM walk "
                        "GROUP BY node ORDER BY min(depth),node LIMIT :maximum"
                    ),
                    {
                        "root": sense_id,
                        "profile": profile_id,
                        "types": list(edge_types),
                        "depth": depth,
                        "maximum": max_nodes,
                    },
                )
            ).all()
            nodes = tuple(UUID(str(item.node)) for item in node_rows)
            edge_rows = (
                await session.execute(
                    text(
                        "SELECT source_sense_id,target_sense_id,relation_type FROM "
                        "lexicon.personal_lexical_relations relation WHERE profile_id=:profile "
                        "AND source_sense_id=ANY(:nodes) AND target_sense_id=ANY(:nodes) "
                        "AND relation_type=ANY(:types) AND NOT EXISTS (SELECT 1 FROM "
                        "lexicon.lexical_relation_retractions retract WHERE retract.profile_id=:profile "
                        "AND retract.relation_id=relation.relation_id) ORDER BY relation_id"
                    ),
                    {"profile": profile_id, "nodes": list(nodes), "types": list(edge_types)},
                )
            ).all()
            graph = tuple(GraphEdge(UUID(str(item.source_sense_id)), UUID(str(item.target_sense_id)), str(item.relation_type)) for item in edge_rows)
            neighborhood = bounded_neighborhood(sense_id, graph, depth=depth, edge_types=frozenset(edge_types), max_nodes=max_nodes)
            return SenseNeighborhoodResponse(sense_id=sense_id, label=str(row["lemma"]), definition=str(row["definition"]), nodes=nodes, edges=tuple({"source": str(edge.source_sense_id), "target": str(edge.target_sense_id), "type": edge.edge_type} for edge in neighborhood.edges), truncated=len(nodes) == max_nodes or neighborhood.truncated, version=1)

    async def list_annotations(self, *, account_id: UUID, profile_id: UUID, limit: int, cursor: str | None) -> LexicalAnnotationPageResponse:
        async with self._session_factory() as session:
            await self._set_actor(session, account_id)
            await self._assert_owner(session, account_id, profile_id)
            after = None if cursor is None else UUID(cursor)
            rows = (
                await session.execute(text("SELECT annotation.annotation_id,annotation.sense_id,annotation.version,revision.body FROM lexicon.lexical_annotations annotation JOIN LATERAL (SELECT body FROM lexicon.lexical_annotation_revisions WHERE annotation_id=annotation.annotation_id ORDER BY version DESC LIMIT 1) revision ON true WHERE annotation.profile_id=:profile AND annotation.deleted_at IS NULL AND (:after::uuid IS NULL OR annotation.annotation_id>:after) ORDER BY annotation.annotation_id LIMIT :fetch"), {"profile": profile_id, "after": after, "fetch": limit + 1})
            ).all()
            page_rows = rows[:limit]
            next_cursor = str(page_rows[-1].annotation_id) if len(rows) > limit else None
            return LexicalAnnotationPageResponse(
                items=tuple(
                    LexicalAnnotationResponse(
                        annotation_id=UUID(str(row.annotation_id)),
                        sense_id=UUID(str(row.sense_id)),
                        body=str(row.body),
                        version=int(row.version),
                    )
                    for row in page_rows
                ),
                next_cursor=next_cursor,
            )
