from types import SimpleNamespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import database_url_from_environment
from polyglot.interfaces.http.app import create_app
from polyglot.modules.content.application import ContentApplicationService
from polyglot.platform.clock import FrozenClock

from .conftest import IDS, NOW, VARIETY_ID, seed_published_catalogue_reference

ORIGIN = "https://polyglot.test"


class StaticIdentity:
    def __init__(self, account_id: UUID, *roles: str) -> None:
        self.account_id = account_id
        self.roles = roles

    async def get_current_session(self, token: str, context: object) -> object:
        del context
        if token != "content-session":
            raise AssertionError("unexpected session token")
        return SimpleNamespace(
            account_id=self.account_id,
            roles=self.roles,
            session_id=IDS["session"],
            csrf_token="content-csrf",
        )


class AlwaysRecentAuthentication:
    async def is_recent(self, **_: object) -> bool:
        return True


@pytest.fixture
async def http_services(migration_session: AsyncSession):
    await seed_published_catalogue_reference(migration_session)
    await migration_session.commit()
    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    identity = StaticIdentity(IDS["author"], "author")
    service = ContentApplicationService(
        factory,
        clock=FrozenClock(NOW),
        reauthentication_policy=AlwaysRecentAuthentication(),
    )
    yield identity, service
    await engine.dispose()


def _headers(*, key: str, version: int | None = None) -> dict[str, str]:
    headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": "content-csrf",
        "Idempotency-Key": key,
    }
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return headers


async def _client(identity: object, service: ContentApplicationService) -> AsyncClient:
    app = create_app(
        test_mode=True,
        identity_service=identity,  # type: ignore[arg-type]
        content_service=service,
        allowed_origin=ORIGIN,
    )
    client = AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN)
    client.cookies.set("__Host-polyglot_session", "content-session", domain="polyglot.test")
    return client


def _create_payload(text: str = "Ciao.") -> dict[str, object]:
    return {
        "content_type": "dialogue",
        "variety_id": str(VARIETY_ID),
        "payload": {"schema_version": 1, "text": text},
        "provenance_id": str(IDS["provenance"]),
        "rights_ref": "rights:fixture:content",
        "pinned_revision_refs": [
            {
                "reference_kind": "skill_revision",
                "revision_id": str(IDS["catalogue_revision"]),
            }
        ],
    }


async def test_http_authoring_flow_exposes_paginated_reads_and_history(http_services) -> None:
    identity, service = http_services
    async with await _client(identity, service) as client:
        created = await client.post(
            "/api/v1/authoring/drafts",
            headers=_headers(key="http-create"),
            json=_create_payload(),
        )
        replay = await client.post(
            "/api/v1/authoring/drafts",
            headers=_headers(key="http-create"),
            json=_create_payload(),
        )
        draft_id = created.json()["content_revision_id"]
        content_id = created.json()["content_id"]
        listed = await client.get("/api/v1/authoring/drafts", params={"limit": 1})
        read = await client.get(f"/api/v1/authoring/drafts/{draft_id}")
        validated = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:validate",
            headers=_headers(key="http-validate", version=1),
            json={"validator_set_revision_id": str(IDS["validator_set"])},
        )
        report_id = validated.json()["report_id"]
        report = await client.get(f"/api/v1/validation-reports/{report_id}")

        identity.account_id = IDS["reviewer"]
        identity.roles = ("reviewer",)
        approved = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:approve",
            headers=_headers(key="http-approve", version=2),
            json={"reason_code": "reviewed.complete"},
        )
        published = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:publish",
            headers=_headers(key="http-publish", version=3),
            json={
                "publication_provenance_id": str(IDS["publication_provenance"]),
                "channel_code": "stable",
                "compatibility_range": ">=2.0.0,<2.1.0",
            },
        )
        retired = await client.post(
            f"/api/v1/content/{content_id}/revisions/{draft_id}:retire",
            headers=_headers(key="http-retire", version=4),
        )
        history = await client.get(f"/api/v1/authoring/content/{content_id}/history")

    assert created.status_code == 201
    assert replay.status_code == 201 and replay.json() == created.json()
    assert listed.status_code == 200 and listed.json()["items"][0]["status"] == "draft"
    assert read.status_code == 200 and read.json()["payload"]["text"] == "Ciao."
    assert validated.status_code == 200 and validated.json()["status"] == "validated"
    assert report.status_code == 200 and report.json()["status"] == "passed"
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert published.status_code == 200 and published.json()["status"] == "published"
    assert retired.status_code == 200 and retired.json()["status"] == "retired"
    assert history.status_code == 200 and history.json()["items"][0]["status"] == "retired"


async def test_http_rejects_bad_transport_stale_version_and_out_of_scope_reads(
    http_services,
) -> None:
    identity, service = http_services
    async with await _client(identity, service) as client:
        cross_origin = await client.post(
            "/api/v1/authoring/drafts",
            headers={**_headers(key="cross"), "Origin": "https://attacker.invalid"},
            json=_create_payload(),
        )
        missing_csrf = await client.post(
            "/api/v1/authoring/drafts",
            headers={"Origin": ORIGIN, "Idempotency-Key": "missing-csrf"},
            json=_create_payload(),
        )
        created = await client.post(
            "/api/v1/authoring/drafts",
            headers=_headers(key="scope-create"),
            json=_create_payload(),
        )
        draft_id = created.json()["content_revision_id"]
        stale = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:validate",
            headers=_headers(key="stale", version=99),
            json={"validator_set_revision_id": str(IDS["validator_set"])},
        )
        identity.account_id = IDS["reviewer"]
        identity.roles = ("learner",)
        forbidden = await client.get("/api/v1/authoring/drafts")
        identity.roles = ("author",)
        out_of_scope = await client.get(f"/api/v1/authoring/drafts/{draft_id}")

    assert cross_origin.status_code == 403
    assert missing_csrf.status_code == 422
    assert stale.status_code == 409 and stale.json()["code"] == "version_conflict"
    assert forbidden.status_code == 403
    assert out_of_scope.status_code == 404
    for response in (cross_origin, missing_csrf, stale, forbidden, out_of_scope):
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["request_id"] == response.headers["X-Request-ID"]


async def test_http_draft_pagination_uses_a_stable_opaque_cursor(http_services) -> None:
    identity, service = http_services
    async with await _client(identity, service) as client:
        first = await client.post(
            "/api/v1/authoring/drafts",
            headers=_headers(key="page-create-first"),
            json=_create_payload("Primo."),
        )
        second = await client.post(
            "/api/v1/authoring/drafts",
            headers=_headers(key="page-create-second"),
            json=_create_payload("Secondo."),
        )
        page_one = await client.get("/api/v1/authoring/drafts", params={"limit": 1})
        page_two = await client.get(
            "/api/v1/authoring/drafts",
            params={"limit": 1, "cursor": page_one.json()["next_cursor"]},
        )

    assert first.status_code == 201 and second.status_code == 201
    assert page_one.status_code == 200 and page_one.json()["next_cursor"]
    assert page_two.status_code == 200
    assert page_one.json()["items"][0]["content_revision_id"] != page_two.json()["items"][0][
        "content_revision_id"
    ]


async def test_http_rejection_is_closed_replayable_and_blocks_publication(http_services) -> None:
    identity, service = http_services
    async with await _client(identity, service) as client:
        created = await client.post(
            "/api/v1/authoring/drafts",
            headers=_headers(key="http-reject-create"),
            json=_create_payload(),
        )
        draft_id = created.json()["content_revision_id"]
        validated = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:validate",
            headers=_headers(key="http-reject-validate", version=1),
            json={"validator_set_revision_id": str(IDS["validator_set"])},
        )
        identity.account_id = IDS["reviewer"]
        identity.roles = ("reviewer",)
        rejected = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:approve",
            headers=_headers(key="http-reject-decision", version=2),
            json={"decision": "rejected", "reason_code": "reviewed.incorrect"},
        )
        replayed = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:approve",
            headers=_headers(key="http-reject-decision", version=2),
            json={"decision": "rejected", "reason_code": "reviewed.incorrect"},
        )
        conflict = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:approve",
            headers=_headers(key="http-reject-decision", version=2),
            json={"decision": "approved", "reason_code": "reviewed.incorrect"},
        )
        publish = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:publish",
            headers=_headers(key="http-reject-publish", version=3),
            json={
                "publication_provenance_id": str(IDS["publication_provenance"]),
                "channel_code": "stable",
                "compatibility_range": ">=2.0.0,<2.1.0",
            },
        )
        invalid = await client.post(
            f"/api/v1/authoring/drafts/{draft_id}:approve",
            headers=_headers(key="http-reject-invalid", version=3),
            json={"decision": "maybe", "reason_code": "reviewed.unknown"},
        )

    assert validated.status_code == 200
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert replayed.status_code == 200 and replayed.json() == rejected.json()
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    assert publish.status_code == 409 and publish.json()["code"] == "invalid_transition"
    assert invalid.status_code == 422 and invalid.json()["code"] == "validation_failed"
    for response in (conflict, publish, invalid):
        assert response.headers["content-type"].startswith("application/problem+json")
