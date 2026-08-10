"""Authenticated W08 vocabulary list and exchange routes."""

# ruff: noqa: E501

from __future__ import annotations

import base64
import binascii
from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, Security
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict, Field

from polyglot.interfaces.http.routes.identity import (
    IDENTITY_PROBLEM_RESPONSES,
    SESSION_COOKIE,
    _context,
    _expected_version,
    _require_origin,
    _session_token,
)
from polyglot.modules.identity.application import CurrentSessionResult, IdentityApplicationService
from polyglot.modules.lexicon.exchange.application import (
    ChangeListMembers,
    CreateImport,
    CreateVocabularyList,
    ImportRunView,
    ListSnapshotView,
    MutationView,
    VocabularyListView,
)
from polyglot.modules.lexicon.exchange.domain import ImportStrategy
from polyglot.modules.lexicon.exchange.security import (
    ImportLimits,
    read_single_safe_zip_entry,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
OriginHeader = Annotated[str, Header(alias="Origin")]
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str, Header(alias="If-Match")]
SessionCookieToken = Annotated[
    str | None,
    Security(APIKeyCookie(name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False)),
]

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    **IDENTITY_PROBLEM_RESPONSES,
    428: IDENTITY_PROBLEM_RESPONSES[422],
}
ETAG_RESPONSES: dict[int | str, dict[str, Any]] = {
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


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateVocabularyListRequest(ClosedModel):
    variety_id: UUID
    list_type: str = Field(pattern="^(manual|editorial|dynamic)$")
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=2_000)
    ordered: bool = True
    color: str | None = Field(default=None, max_length=32)
    tags: tuple[str, ...] = Field(default=(), max_length=100)
    query_definition: dict[str, JsonValue] | None = None
    member_sense_ids: tuple[UUID, ...] = Field(default=(), max_length=10_000)
    created_at: datetime


class ReviseVocabularyListRequest(ClosedModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    purpose: str | None = Field(default=None, min_length=1, max_length=2_000)
    ordered: bool | None = None
    color: str | None = Field(default=None, max_length=32)
    tags: tuple[str, ...] | None = Field(default=None, max_length=100)
    query_definition: dict[str, JsonValue] | None = None
    revised_at: datetime


class ChangeListMembersRequest(ClosedModel):
    add_sense_ids: tuple[UUID, ...] = Field(default=(), max_length=10_000)
    remove_sense_ids: tuple[UUID, ...] = Field(default=(), max_length=10_000)
    changed_at: datetime


class AtRequest(ClosedModel):
    at: datetime


class CloneVocabularyListRequest(ClosedModel):
    target_profile_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cloned_at: datetime


class MergeVocabularyListsRequest(ClosedModel):
    source_list_ids: tuple[UUID, ...] = Field(min_length=2, max_length=100)
    target_profile_id: UUID
    name: str = Field(min_length=1, max_length=200)
    strategy: str = Field(pattern="^(union|intersection|ordered_union)$")
    merged_at: datetime


class PublishVocabularyListSnapshotRequest(ClosedModel):
    license_ref: str = Field(min_length=1, max_length=500)
    provenance_id: UUID
    published_at: datetime


class CreateImportRequest(ClosedModel):
    format_id: str = Field(min_length=1, max_length=80)
    encoding: str = Field(min_length=1, max_length=40)
    content_base64: str = Field(min_length=1, max_length=14_000_000)
    archive: bool = False
    strategy: ImportStrategy
    created_at: datetime
    expires_at: datetime


class ResolveImportConflictRequest(ClosedModel):
    preview_checksum: str = Field(pattern="^[0-9a-f]{64}$")
    action: str = Field(min_length=1, max_length=40)
    decided_at: datetime


class CommitImportRequest(ClosedModel):
    preview_checksum: str = Field(pattern="^[0-9a-f]{64}$")
    committed_at: datetime


class RequestExportRequest(ClosedModel):
    scope: dict[str, JsonValue]
    requested_at: datetime


class VocabularyListResponse(ClosedModel):
    list_id: UUID
    profile_id: UUID
    variety_id: UUID
    list_type: str
    status: str
    version: int
    revision_id: UUID
    revision_no: int
    name: str
    purpose: str
    ordered: bool
    color: str | None
    tags: tuple[str, ...]
    query_definition: dict[str, JsonValue] | None
    member_sense_ids: tuple[UUID, ...]


class VocabularyListPageResponse(ClosedModel):
    items: tuple[VocabularyListResponse, ...]
    next_cursor: str | None


class ListSnapshotResponse(ClosedModel):
    snapshot_id: UUID
    list_id: UUID
    profile_id: UUID
    source_revision_id: UUID
    checksum: str
    member_sense_revision_ids: tuple[UUID, ...]


class ImportRunResponse(ClosedModel):
    import_id: UUID
    profile_id: UUID
    format_id: str
    status: str
    strategy: str
    preview_checksum: str
    catalogue_version: str
    version: int
    unresolved_conflicts: int
    created_refs: tuple[str, ...]
    reused_refs: tuple[str, ...]


class ResourceMutationResponse(ClosedModel):
    resource_id: UUID
    version: int
    status: str


class ResourcePageResponse(ClosedModel):
    items: tuple[dict[str, JsonValue], ...]
    next_cursor: str | None


class ExchangeService(Protocol):
    async def create_list(self, actor_id: UUID, profile_id: UUID, command: CreateVocabularyList, *, idempotency_key: str) -> VocabularyListView: ...
    async def change_members(self, actor_id: UUID, list_id: UUID, command: ChangeListMembers, *, expected_version: int, idempotency_key: str) -> VocabularyListView: ...
    async def freeze_list(self, actor_id: UUID, list_id: UUID, *, expected_version: int, frozen_at: datetime, idempotency_key: str) -> ListSnapshotView: ...
    async def get_list(self, actor_id: UUID, list_id: UUID) -> VocabularyListView: ...
    async def create_import(self, actor_id: UUID, profile_id: UUID, command: CreateImport, *, idempotency_key: str) -> ImportRunView: ...
    async def get_import(self, actor_id: UUID, import_id: UUID) -> ImportRunView: ...
    async def current_catalogue_version(self, actor_id: UUID, profile_id: UUID) -> str: ...
    async def commit_import(self, actor_id: UUID, import_id: UUID, *, preview_checksum: str, current_catalogue_version: str, expected_version: int, committed_at: datetime, idempotency_key: str) -> ImportRunView: ...
    async def revert_import(self, actor_id: UUID, import_id: UUID, *, expected_version: int, reverted_at: datetime, idempotency_key: str) -> ImportRunView: ...
    async def execute_command(
        self,
        *,
        command_name: str,
        actor_id: UUID,
        resource_id: UUID,
        payload: dict[str, Any],
        idempotency_key: str,
        expected_version: int | None,
        session_id: UUID | None = None,
    ) -> MutationView: ...
    async def list_resources(
        self,
        *,
        actor_id: UUID,
        resource_type: str,
        profile_id: UUID | None,
        limit: int,
        cursor: str | None,
        resource_id: UUID | None = None,
    ) -> tuple[tuple[dict[str, Any], ...], str | None]: ...


def _list_response(view: VocabularyListView) -> VocabularyListResponse:
    return VocabularyListResponse.model_validate(view, from_attributes=True)


def _import_response(view: ImportRunView) -> ImportRunResponse:
    return ImportRunResponse(
        **{
            **asdict(view),
            "strategy": view.strategy.value,
        }
    )


def exchange_router(
    service: ExchangeService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> ExchangeService:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    async def session_for(
        request: Request,
        token: str | None,
        csrf: str | None = None,
        origin: str | None = None,
    ) -> CurrentSessionResult:
        if identity_service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        if origin is not None:
            _require_origin(origin, allowed_origin)
        current = await identity_service.get_current_session(_session_token(token), _context(request))
        if csrf is not None and csrf != current.csrf_token:
            raise DomainError(ErrorCode.FORBIDDEN)
        return current

    def expected(value: str) -> int:
        try:
            return _expected_version(value)
        except ValueError as error:
            raise HTTPException(status_code=428, detail="If-Match is required") from error

    def etag(response: Response, version: int) -> None:
        response.headers["ETag"] = f'"{version}"'

    async def generic(
        *,
        command_name: str,
        current: CurrentSessionResult,
        resource_id: UUID,
        payload: dict[str, Any],
        idempotency_key: str,
        expected_version: int | None,
        session_id: UUID | None = None,
    ) -> ResourceMutationResponse:
        result = await application_service().execute_command(
            command_name=command_name,
            actor_id=current.account_id,
            resource_id=resource_id,
            payload=payload,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            session_id=session_id,
        )
        return ResourceMutationResponse.model_validate(result, from_attributes=True)

    @router.post("/api/v1/language-profiles/{profile_id}/vocabulary-lists", operation_id="create_vocabulary_list", response_model=VocabularyListResponse, status_code=201, responses=ETAG_RESPONSES)
    async def create_vocabulary_list(profile_id: UUID, payload: CreateVocabularyListRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, token: SessionCookieToken = None) -> VocabularyListResponse:
        current = await session_for(request, token, csrf, origin)
        view = await application_service().create_list(current.account_id, profile_id, CreateVocabularyList(**payload.model_dump()), idempotency_key=idempotency_key)
        etag(response, view.version)
        return _list_response(view)

    @router.patch("/api/v1/vocabulary-lists/{list_id}", operation_id="revise_vocabulary_list", response_model=ResourceMutationResponse, responses=ETAG_RESPONSES)
    async def revise_vocabulary_list(list_id: UUID, payload: ReviseVocabularyListRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, if_match: IfMatchHeader, token: SessionCookieToken = None) -> ResourceMutationResponse:
        current = await session_for(request, token, csrf, origin)
        result = await generic(command_name="ReviseVocabularyList", current=current, resource_id=list_id, payload=payload.model_dump(), idempotency_key=idempotency_key, expected_version=expected(if_match))
        etag(response, result.version)
        return result

    @router.post("/api/v1/vocabulary-lists/{list_id}/members:batch", operation_id="change_list_members", response_model=VocabularyListResponse, responses=ETAG_RESPONSES)
    async def change_list_members(list_id: UUID, payload: ChangeListMembersRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, if_match: IfMatchHeader, token: SessionCookieToken = None) -> VocabularyListResponse:
        current = await session_for(request, token, csrf, origin)
        view = await application_service().change_members(current.account_id, list_id, ChangeListMembers(**payload.model_dump()), expected_version=expected(if_match), idempotency_key=idempotency_key)
        etag(response, view.version)
        return _list_response(view)

    @router.post("/api/v1/vocabulary-lists/{list_id}:snapshot", operation_id="freeze_vocabulary_list", response_model=ListSnapshotResponse, responses=ETAG_RESPONSES)
    async def freeze_vocabulary_list(list_id: UUID, payload: AtRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, if_match: IfMatchHeader, token: SessionCookieToken = None) -> ListSnapshotResponse:
        current = await session_for(request, token, csrf, origin)
        view = await application_service().freeze_list(current.account_id, list_id, expected_version=expected(if_match), frozen_at=payload.at, idempotency_key=idempotency_key)
        etag(response, 1)
        return ListSnapshotResponse.model_validate(view, from_attributes=True)

    async def generic_unversioned(command_name: str, resource_id: UUID, payload: ClosedModel, request: Request, idempotency_key: str, origin: str, csrf: str, token: str | None) -> ResourceMutationResponse:
        current = await session_for(request, token, csrf, origin)
        return await generic(command_name=command_name, current=current, resource_id=resource_id, payload=payload.model_dump(), idempotency_key=idempotency_key, expected_version=None)

    @router.post("/api/v1/vocabulary-lists/{list_id}:clone", operation_id="clone_vocabulary_list", response_model=ResourceMutationResponse, responses=PROBLEM_RESPONSES)
    async def clone_vocabulary_list(list_id: UUID, payload: CloneVocabularyListRequest, request: Request, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, token: SessionCookieToken = None) -> ResourceMutationResponse:
        return await generic_unversioned("CloneVocabularyList", list_id, payload, request, idempotency_key, origin, csrf, token)

    @router.post("/api/v1/vocabulary-lists:merge", operation_id="merge_vocabulary_lists", response_model=ResourceMutationResponse, responses=PROBLEM_RESPONSES)
    async def merge_vocabulary_lists(payload: MergeVocabularyListsRequest, request: Request, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, token: SessionCookieToken = None) -> ResourceMutationResponse:
        return await generic_unversioned("MergeVocabularyLists", payload.target_profile_id, payload, request, idempotency_key, origin, csrf, token)

    @router.post("/api/v1/vocabulary-lists/{list_id}/snapshots/{snapshot_id}:publish", operation_id="publish_vocabulary_list_snapshot", response_model=ResourceMutationResponse, responses=ETAG_RESPONSES)
    async def publish_vocabulary_list_snapshot(list_id: UUID, snapshot_id: UUID, payload: PublishVocabularyListSnapshotRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, if_match: IfMatchHeader, token: SessionCookieToken = None) -> ResourceMutationResponse:
        current = await session_for(request, token, csrf, origin)
        result = await generic(command_name="PublishVocabularyListSnapshot", current=current, resource_id=snapshot_id, payload={**payload.model_dump(), "list_id": list_id}, idempotency_key=idempotency_key, expected_version=expected(if_match))
        etag(response, result.version)
        return result

    @router.post("/api/v1/shared-vocabulary-lists/{publication_id}:retire", operation_id="retire_shared_vocabulary_list", response_model=ResourceMutationResponse, responses=ETAG_RESPONSES)
    async def retire_shared_vocabulary_list(publication_id: UUID, payload: AtRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, if_match: IfMatchHeader, token: SessionCookieToken = None) -> ResourceMutationResponse:
        current = await session_for(request, token, csrf, origin)
        result = await generic(command_name="RetireSharedVocabularyList", current=current, resource_id=publication_id, payload=payload.model_dump(), idempotency_key=idempotency_key, expected_version=expected(if_match))
        etag(response, result.version)
        return result

    @router.post("/api/v1/language-profiles/{profile_id}/imports", operation_id="create_import", response_model=ImportRunResponse, status_code=201, responses=ETAG_RESPONSES)
    async def create_import(profile_id: UUID, payload: CreateImportRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, token: SessionCookieToken = None) -> ImportRunResponse:
        current = await session_for(request, token, csrf, origin)
        try:
            raw = base64.b64decode(payload.content_base64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid base64 import") from error
        if payload.archive:
            raw = read_single_safe_zip_entry(raw, ImportLimits())
        catalogue_version = await application_service().current_catalogue_version(current.account_id, profile_id)
        view = await application_service().create_import(current.account_id, profile_id, CreateImport(format_id=payload.format_id, encoding=payload.encoding, payload=raw, strategy=payload.strategy, catalogue_version=catalogue_version, created_at=payload.created_at, expires_at=payload.expires_at), idempotency_key=idempotency_key)
        etag(response, view.version)
        return _import_response(view)

    @router.post("/api/v1/imports/{import_id}/conflicts/{conflict_id}:resolve", operation_id="resolve_import_conflict", response_model=ResourceMutationResponse, responses=ETAG_RESPONSES)
    async def resolve_import_conflict(import_id: UUID, conflict_id: UUID, payload: ResolveImportConflictRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, if_match: IfMatchHeader, token: SessionCookieToken = None) -> ResourceMutationResponse:
        current = await session_for(request, token, csrf, origin)
        result = await generic(command_name="ResolveImportConflict", current=current, resource_id=conflict_id, payload={**payload.model_dump(), "import_id": import_id}, idempotency_key=idempotency_key, expected_version=expected(if_match))
        etag(response, result.version)
        return result

    @router.post("/api/v1/imports/{import_id}:commit", operation_id="commit_import", response_model=ImportRunResponse, responses=ETAG_RESPONSES)
    async def commit_import(import_id: UUID, payload: CommitImportRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, if_match: IfMatchHeader, token: SessionCookieToken = None) -> ImportRunResponse:
        current = await session_for(request, token, csrf, origin)
        current_run = await application_service().get_import(current.account_id, import_id)
        catalogue_version = await application_service().current_catalogue_version(current.account_id, current_run.profile_id)
        view = await application_service().commit_import(current.account_id, import_id, preview_checksum=payload.preview_checksum, current_catalogue_version=catalogue_version, expected_version=expected(if_match), committed_at=payload.committed_at, idempotency_key=idempotency_key)
        etag(response, view.version)
        return _import_response(view)

    @router.post("/api/v1/imports/{import_id}:revert", operation_id="revert_import", response_model=ImportRunResponse, responses=ETAG_RESPONSES)
    async def revert_import(import_id: UUID, payload: AtRequest, request: Request, response: Response, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, if_match: IfMatchHeader, token: SessionCookieToken = None) -> ImportRunResponse:
        current = await session_for(request, token, csrf, origin)
        view = await application_service().revert_import(current.account_id, import_id, expected_version=expected(if_match), reverted_at=payload.at, idempotency_key=idempotency_key)
        etag(response, view.version)
        return _import_response(view)

    @router.post("/api/v1/language-profiles/{profile_id}/exports", operation_id="request_export", response_model=ResourceMutationResponse, status_code=202, responses=PROBLEM_RESPONSES)
    async def request_export(profile_id: UUID, payload: RequestExportRequest, request: Request, idempotency_key: IdempotencyKey, origin: OriginHeader, csrf: CsrfHeader, token: SessionCookieToken = None) -> ResourceMutationResponse:
        current = await session_for(request, token, csrf, origin)
        return await generic(command_name="RequestExport", current=current, resource_id=profile_id, payload=payload.model_dump(), idempotency_key=idempotency_key, expected_version=None, session_id=current.session_id)

    @router.get("/api/v1/vocabulary-lists/{id}", operation_id="get_vocabulary_list", response_model=VocabularyListResponse, responses=PROBLEM_RESPONSES)
    async def get_vocabulary_list(id: UUID, request: Request, token: SessionCookieToken = None) -> VocabularyListResponse:
        current = await session_for(request, token)
        return _list_response(await application_service().get_list(current.account_id, id))

    @router.get("/api/v1/imports/{id}", operation_id="get_import", response_model=ImportRunResponse, responses=PROBLEM_RESPONSES)
    async def get_import(id: UUID, request: Request, token: SessionCookieToken = None) -> ImportRunResponse:
        current = await session_for(request, token)
        return _import_response(await application_service().get_import(current.account_id, id))

    def make_list_endpoint(resource_type: str):
        async def list_endpoint(
            request: Request,
            profile_id: Annotated[UUID | None, Query()] = None,
            limit: Annotated[int, Query(ge=1, le=100)] = 50,
            cursor: Annotated[
                str | None, Query(min_length=1, max_length=1024)
            ] = None,
            token: SessionCookieToken = None,
        ) -> ResourcePageResponse:
            current = await session_for(request, token)
            items, next_cursor = await application_service().list_resources(
                actor_id=current.account_id,
                resource_type=resource_type,
                profile_id=profile_id,
                limit=limit,
                cursor=cursor,
            )
            return ResourcePageResponse(items=items, next_cursor=next_cursor)

        return list_endpoint

    for route, operation_id, resource_type in (
        ("/api/v1/vocabulary-lists", "list_vocabulary_lists", "vocabulary_list"),
        ("/api/v1/shared-vocabulary-lists", "list_shared_vocabulary_lists", "shared_list"),
    ):
        list_endpoint = make_list_endpoint(resource_type)
        list_endpoint.__name__ = operation_id
        router.add_api_route(route, list_endpoint, methods=["GET"], operation_id=operation_id, response_model=ResourcePageResponse, responses=PROBLEM_RESPONSES)

    def make_get_endpoint(resource_type: str):
        async def get_endpoint(
            id: UUID,
            request: Request,
            token: SessionCookieToken = None,
        ) -> dict[str, JsonValue]:
            current = await session_for(request, token)
            items, _ = await application_service().list_resources(
                actor_id=current.account_id,
                resource_type=resource_type,
                resource_id=id,
                profile_id=None,
                limit=1,
                cursor=None,
            )
            if not items:
                raise DomainError(ErrorCode.NOT_FOUND)
            return items[0]

        return get_endpoint

    for route, operation_id, resource_type in (
        ("/api/v1/shared-vocabulary-lists/{id}", "get_shared_vocabulary_list", "shared_list"),
        ("/api/v1/exports/{id}", "get_export", "export"),
    ):
        get_endpoint = make_get_endpoint(resource_type)
        get_endpoint.__name__ = operation_id
        router.add_api_route(route, get_endpoint, methods=["GET"], operation_id=operation_id, response_model=dict[str, JsonValue], responses=PROBLEM_RESPONSES)

    return router
