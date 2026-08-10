"""W03 HTTP contracts: an authenticated learner owns every profile operation."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.modules.identity.domain import FakeOidcProvider, SessionSecrets
from polyglot.platform.clock import FrozenClock

ORIGIN = "https://polyglot.test"
TARGET = "019fe900-5000-7000-8001-000000000001"
NATIVE = "019fe900-5000-7000-8001-000000000002"


@pytest.fixture
async def services() -> tuple[IdentityApplicationService, object]:
    from polyglot.modules.language_profiles.application import LanguageProfileApplicationService

    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    clock = FrozenClock(datetime(2026, 8, 10, 12, 0, tzinfo=UTC))
    identity = IdentityApplicationService(
        factory,
        clock=clock,
        session_secrets=SessionSecrets.from_key(b"w03-contract-session-secret-at-least-32b"),
        oidc_provider=FakeOidcProvider({}),
    )
    yield identity, LanguageProfileApplicationService(factory, clock=clock)
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_w03_contract_database() -> None:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE identity.accounts CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.domain_events CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.command_receipts CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.outbox_messages CASCADE"))
    await engine.dispose()


async def _client(services: tuple[IdentityApplicationService, object]) -> AsyncClient:
    from polyglot.interfaces.http.app import create_app

    identity, language_profiles = services
    app = create_app(
        test_mode=True,
        identity_service=identity,
        language_profile_service=language_profiles,
        allowed_origin=ORIGIN,
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN)


async def _login(client: AsyncClient, identifier: str) -> tuple[str, str]:
    registered = await client.post(
        "/api/v1/accounts",
        headers={"Origin": ORIGIN, "Idempotency-Key": f"register-{identifier}"},
        json={
            "provider_type": "local_password",
            "identifier": identifier,
            "password": "correct horse battery staple",
        },
    )
    assert registered.status_code == 201
    authenticated = await client.post(
        "/api/v1/session",
        headers={"Origin": ORIGIN, "Idempotency-Key": f"session-{identifier}"},
        json={
            "provider_type": "local_password",
            "identifier": identifier,
            "password": "correct horse battery staple",
        },
    )
    assert authenticated.status_code == 201
    return registered.json()["account_id"], authenticated.json()["csrf_token"]


async def test_profile_commands_are_authenticated_idempotent_and_owner_scoped(
    services: tuple[IdentityApplicationService, object],
) -> None:
    async with await _client(services) as client:
        account_id, csrf = await _login(client, "w03-owner@example.test")
        created = await client.post(
            "/api/v1/language-profiles",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "create-it-profile",
            },
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        replay = await client.post(
            "/api/v1/language-profiles",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "create-it-profile",
            },
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        profile_id = created.json()["profile_id"]
        updated = await client.patch(
            f"/api/v1/language-profiles/{profile_id}/goals",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "If-Match": '"1"',
                "Idempotency-Key": "update-goals",
            },
            json={"goals": ["travel", "conversation"]},
        )
        listed = await client.get("/api/v1/language-profiles")

    assert created.status_code == 201
    assert created.headers["etag"] == '"1"'
    assert created.json()["account_id"] == account_id
    assert replay.status_code == 201 and replay.json() == created.json()
    assert updated.status_code == 200 and updated.json()["version"] == 2
    assert updated.headers["etag"] == '"2"'
    assert listed.status_code == 200
    assert listed.json()["items"][0]["goals"] == ["travel", "conversation"]


async def test_mutating_existing_resource_without_if_match_returns_428(
    services: tuple[IdentityApplicationService, object],
) -> None:
    async with await _client(services) as client:
        _, csrf = await _login(client, "w03-precondition@example.test")
        profile = await client.post(
            "/api/v1/language-profiles",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": "create-pre"},
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        response = await client.patch(
            f"/api/v1/language-profiles/{profile.json()['profile_id']}/goals",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "goals-without-precondition",
            },
            json={"goals": ["travel"]},
        )

    assert response.status_code == 428


async def test_diagnostic_is_resumable_for_exactly_twenty_four_hours_without_credit(
    services: tuple[IdentityApplicationService, object],
) -> None:
    async with await _client(services) as client:
        _, csrf = await _login(client, "w03-diagnostic@example.test")
        profile = await client.post(
            "/api/v1/language-profiles",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "create-diagnostic-profile",
            },
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        started = await client.post(
            f"/api/v1/language-profiles/{profile.json()['profile_id']}/diagnostics",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "If-Match": '"1"',
                "Idempotency-Key": "start-diagnostic",
            },
            json={
                "policy_revision_id": "019fe900-5000-7000-8001-000000000003",
                "pack_revision_id": "019fe900-5000-7000-8001-000000000004",
                "seed": "offline-fixture",
            },
        )
        summary = await client.get(f"/api/v1/diagnostics/{started.json()['diagnostic_run_id']}")

    assert started.status_code == 201
    assert summary.status_code == 200
    assert summary.json()["status"] == "in_progress"
    assert summary.json()["expires_at"] == "2026-08-11T12:00:00Z"
    assert "mastery" not in summary.json()


async def test_client_cannot_submit_normative_diagnostic_scores_or_force_active(
    services: tuple[IdentityApplicationService, object],
) -> None:
    async with await _client(services) as client:
        _, csrf = await _login(client, "w03-forged-placement@example.test")
        profile = await client.post(
            "/api/v1/language-profiles",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": "create-forged"},
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        started = await client.post(
            f"/api/v1/language-profiles/{profile.json()['profile_id']}/diagnostics",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "If-Match": '"1"',
                "Idempotency-Key": "start-forged",
            },
            json={
                "policy_revision_id": "019fe900-5000-7000-8001-000000000003",
                "pack_revision_id": "019fe900-5000-7000-8001-000000000004",
                "seed": "offline-fixture",
            },
        )
        forged = await client.post(
            f"/api/v1/diagnostics/{started.json()['diagnostic_run_id']}/responses",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "If-Match": '"1"',
                "Idempotency-Key": "forge-score",
            },
            json={
                "item_revision_id": "019fe900-5000-7000-8001-000000000005",
                "ordinal": 1,
                "answer": {"value": "ciao"},
                "target": "foundations",
                "score": 1,
                "confidence": 1,
                "evaluable": True,
            },
        )

    assert forged.status_code == 422
