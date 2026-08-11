"""End-to-end W03 foundation contracts backed by PostgreSQL and W04F."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)
from polyglot.modules.catalogue.core.domain import PublishedFoundationCatalogue
from polyglot.modules.catalogue.core.fixtures import load_catalogue_fixture
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.modules.identity.domain import FakeOidcProvider, SessionSecrets

ROOT = Path(__file__).resolve().parents[4]
CATALOGUE = load_catalogue_fixture(ROOT / "fixtures/canonical/FX-CATALOGUE-IT").foundations
ORIGIN = "https://polyglot.test"
TARGET = "019fe900-5000-7000-8001-000000000001"
NATIVE = "019fe900-5000-7000-8001-000000000002"
POLICY = "019fe900-5000-7000-8001-000000000003"


@dataclass
class MutableClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant

    def advance(self, delta: timedelta) -> None:
        self.instant += delta


class StaticCatalogueReader:
    def __init__(self, catalogue: PublishedFoundationCatalogue | None) -> None:
        self.catalogue = catalogue

    async def read_foundations(
        self, *, pack_revision_id: UUID
    ) -> PublishedFoundationCatalogue | None:
        if self.catalogue is None or self.catalogue.definition.pack_revision_id != pack_revision_id:
            return None
        return self.catalogue


@pytest.fixture
async def foundation_services() -> tuple[IdentityApplicationService, Any, MutableClock]:
    from polyglot.modules.language_profiles.application import LanguageProfileApplicationService

    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    clock = MutableClock(datetime(2026, 8, 10, 12, 0, tzinfo=UTC))
    identity = IdentityApplicationService(
        factory,
        clock=clock,
        session_secrets=SessionSecrets.from_key(b"w03-foundation-session-secret-at-least-32b"),
        oidc_provider=FakeOidcProvider({}),
    )
    service = LanguageProfileApplicationService(
        factory,
        clock=clock,
        catalogue_reader=StaticCatalogueReader(CATALOGUE),
    )
    yield identity, service, clock
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_foundation_contract_database() -> None:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE identity.accounts CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.domain_events CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.command_receipts CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.outbox_messages CASCADE"))
    await engine.dispose()


async def _client(services: tuple[IdentityApplicationService, Any, MutableClock]) -> AsyncClient:
    from polyglot.interfaces.http.app import create_app

    identity, language_profiles, _ = services
    app = create_app(
        test_mode=True,
        identity_service=identity,
        language_profile_service=language_profiles,
        catalogue_service=StaticCatalogueReader(CATALOGUE),
        allowed_origin=ORIGIN,
    )
    return AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN)


async def _login(client: AsyncClient) -> str:
    identifier = "w03-foundations@example.test"
    registered = await client.post(
        "/api/v1/accounts",
        headers={"Origin": ORIGIN, "Idempotency-Key": "register-foundations"},
        json={
            "provider_type": "local_password",
            "identifier": identifier,
            "password": "correct horse battery staple",
        },
    )
    assert registered.status_code == 201
    return await _authenticate(client, "session-foundations")


async def _authenticate(client: AsyncClient, idempotency_key: str) -> str:
    identifier = "w03-foundations@example.test"
    authenticated = await client.post(
        "/api/v1/session",
        headers={"Origin": ORIGIN, "Idempotency-Key": idempotency_key},
        json={
            "provider_type": "local_password",
            "identifier": identifier,
            "password": "correct horse battery staple",
        },
    )
    assert authenticated.status_code == 201
    return authenticated.json()["csrf_token"]


def _headers(csrf: str, key: str, version: int | None = None) -> dict[str, str]:
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": key}
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return headers


async def _profile_in_foundations(client: AsyncClient, csrf: str) -> tuple[str, int]:
    created = await client.post(
        "/api/v1/language-profiles",
        headers=_headers(csrf, "create-foundation-profile"),
        json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
    )
    profile_id = created.json()["profile_id"]
    diagnostic = await client.post(
        f"/api/v1/language-profiles/{profile_id}/diagnostics",
        headers=_headers(csrf, "start-foundation-diagnostic", 1),
        json={
            "policy_revision_id": POLICY,
            "pack_revision_id": str(CATALOGUE.definition.pack_revision_id),
            "seed": "P-ABS",
        },
    )
    assert diagnostic.status_code == 201
    selected = (
        CATALOGUE.definition.blocks[0].items[0],
        CATALOGUE.definition.blocks[0].items[10],
        *CATALOGUE.definition.blocks[2].items,
        *CATALOGUE.definition.blocks[3].items,
    )
    values = (
        "incorrect-1",
        "incorrect-2",
        selected[2].checker_values[0],
        "incorrect-3",
        "incorrect-4",
        selected[5].checker_values[0],
    )
    diagnostic_version = 1
    for ordinal, (item, value) in enumerate(zip(selected, values, strict=True), start=1):
        submitted = await client.post(
            f"/api/v1/diagnostics/{diagnostic.json()['diagnostic_run_id']}/responses",
            headers=_headers(csrf, f"diagnostic-answer-{ordinal}", diagnostic_version),
            json={
                "item_revision_id": str(item.item_revision_id),
                "ordinal": ordinal,
                "answer": {"value": value},
            },
        )
        assert submitted.status_code == 200, submitted.text
        diagnostic_version += 1
    completed = await client.post(
        f"/api/v1/diagnostics/{diagnostic.json()['diagnostic_run_id']}:complete",
        headers=_headers(csrf, "complete-foundation-diagnostic", diagnostic_version),
    )
    assert completed.status_code == 200, completed.text
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE language_profiles.learner_language_profiles "
                "SET status = 'foundations', current_phase = 'foundations', "
                "version = version + 1, updated_at = :now WHERE profile_id = :profile_id"
            ),
            {
                "profile_id": UUID(profile_id),
                "now": datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
            },
        )
    await engine.dispose()
    profile = await client.get(f"/api/v1/language-profiles/{profile_id}")
    assert profile.json()["status"] == "foundations"
    return profile_id, profile.json()["version"]


def _correct_answers() -> list[dict[str, object]]:
    answers = [
        {
            "item_revision_id": str(item.item_revision_id),
            "answer": {"value": item.checker_values[0] if item.checker_values else "audio"},
            "revealed": False,
        }
        for block in CATALOGUE.definition.blocks
        for item in block.items
    ]
    assert len(answers) == 32
    assert len({item["item_revision_id"] for item in answers}) == 32
    return answers


async def test_foundation_run_uses_published_blocks_and_completes_only_after_delayed_session(
    foundation_services: tuple[IdentityApplicationService, Any, MutableClock],
) -> None:
    _, _, clock = foundation_services
    async with await _client(foundation_services) as client:
        csrf = await _login(client)
        profile_id, profile_version = await _profile_in_foundations(client, csrf)
        started = await client.post(
            f"/api/v1/language-profiles/{profile_id}/foundation-runs",
            headers=_headers(csrf, "start-foundation-run", profile_version),
            json={
                "pack_revision_id": str(CATALOGUE.definition.pack_revision_id),
                "foundation_revision_id": str(CATALOGUE.definition.foundation_revision_id),
                "seed": "FX-IT-FOUND",
            },
        )
        assert started.status_code == 201, started.text
        assert started.headers["etag"] == '"1"'
        run_id = started.json()["foundation_run_id"]

        first_payload = {"answers": _correct_answers()}
        first_headers = _headers(csrf, "foundation-session-1", 1)
        first = await client.post(
            f"/api/v1/foundation-runs/{run_id}:complete",
            headers=first_headers,
            json=first_payload,
        )
        assert first.status_code == 200
        assert first.json()["status"] == "interrupted"
        assert first.json()["session_count"] == 1
        assert first.json()["gate_passed"] is False
        assert "two_sessions_required" in first.json()["gate_reasons"]
        fetched = await client.get(f"/api/v1/foundation-runs/{run_id}")
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["session_count"] == 1
        assert fetched.json()["gate_passed"] is False
        assert fetched.json()["gate_reasons"] == first.json()["gate_reasons"]
        first_replay = await client.post(
            f"/api/v1/foundation-runs/{run_id}:complete",
            headers=first_headers,
            json=first_payload,
        )
        assert first_replay.status_code == 200, first_replay.text
        assert first_replay.json() == first.json()
        assert first_replay.headers["etag"] == first.headers["etag"] == '"2"'

        conflicting_payload = {"answers": _correct_answers()}
        conflicting_payload["answers"][0]["answer"] = {"value": "different-answer"}
        conflict = await client.post(
            f"/api/v1/foundation-runs/{run_id}:complete",
            headers=first_headers,
            json=conflicting_payload,
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "idempotency_conflict"

        clock.advance(timedelta(hours=24))
        csrf = await _authenticate(client, "session-foundations-day-2")
        second_payload = {"answers": _correct_answers()}
        second_headers = _headers(csrf, "foundation-session-2", 2)
        second = await client.post(
            f"/api/v1/foundation-runs/{run_id}:complete",
            headers=second_headers,
            json=second_payload,
        )
        assert second.status_code == 200
        assert second.headers["etag"] == '"3"'
        assert second.json()["status"] == "completed"
        assert second.json()["gate_passed"] is True
        second_replay = await client.post(
            f"/api/v1/foundation-runs/{run_id}:complete",
            headers=second_headers,
            json=second_payload,
        )
        assert second_replay.status_code == 200, second_replay.text
        assert second_replay.json() == second.json()
        assert second_replay.headers["etag"] == second.headers["etag"] == '"3"'
        profile = await client.get(f"/api/v1/language-profiles/{profile_id}")
        assert profile.json()["status"] == "active"

    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.connect() as connection:
        blocks = await connection.scalar(
            text(
                "SELECT count(*) FROM language_profiles.foundation_run_blocks "
                "WHERE foundation_run_id = :run_id"
            ),
            {"run_id": UUID(run_id)},
        )
        measures = (
            await connection.execute(
                text(
                    "SELECT item_revision_id, criterion, evaluable, score "
                    "FROM language_profiles.foundation_measurements "
                    "WHERE foundation_run_id = :run_id "
                    "ORDER BY measured_at, item_revision_id"
                ),
                {"run_id": UUID(run_id)},
            )
        ).all()
        gate_count = await connection.scalar(
            text(
                "SELECT count(*) FROM language_profiles.foundation_gate_results "
                "WHERE foundation_run_id = :run_id"
            ),
            {"run_id": UUID(run_id)},
        )
        events = set(
            (
                await connection.execute(
                    text(
                        "SELECT event_type FROM platform.domain_events "
                        "WHERE aggregate_id = :run_id"
                    ),
                    {"run_id": UUID(run_id)},
                )
            ).scalars()
        )
        outbox_count = await connection.scalar(
            text(
                "SELECT count(*) FROM platform.outbox_messages message "
                "JOIN platform.domain_events event ON event.event_id = message.event_id "
                "WHERE event.aggregate_id = :run_id "
                "AND event.event_type = 'foundation_gate_completed'"
            ),
            {"run_id": UUID(run_id)},
        )
        receipt_count = await connection.scalar(
            text(
                "SELECT count(*) FROM platform.command_receipts "
                "WHERE command_type = 'CompleteFoundationGate' AND aggregate_id = :run_id"
            ),
            {"run_id": UUID(run_id)},
        )
    await engine.dispose()
    assert blocks == 5
    assert len(measures) == 64
    assert sum(not row.evaluable and row.score is None for row in measures) == 2
    assert sum(row.criterion == "grapheme_sound_discrimination" for row in measures) == 20
    assert sum(row.criterion == "targeted_reading" for row in measures) == 20
    assert sum(row.criterion == "survival_exchange" for row in measures) == 10
    for session_items in (measures[:32], measures[32:]):
        assert len({row.item_revision_id for row in session_items}) == 32
    assert gate_count == 2
    assert "foundation_gate_completed" in events
    assert outbox_count == 1
    assert receipt_count == 2


async def test_foundation_commands_require_if_match_and_reject_missing_pack(
    foundation_services: tuple[IdentityApplicationService, Any, MutableClock],
) -> None:
    async with await _client(foundation_services) as client:
        csrf = await _login(client)
        profile_id, profile_version = await _profile_in_foundations(client, csrf)
        missing_precondition = await client.post(
            f"/api/v1/language-profiles/{profile_id}/foundation-runs",
            headers=_headers(csrf, "missing-if-match"),
            json={
                "pack_revision_id": str(CATALOGUE.definition.pack_revision_id),
                "foundation_revision_id": str(CATALOGUE.definition.foundation_revision_id),
                "seed": "missing-header",
            },
        )
        missing_pack = await client.post(
            f"/api/v1/language-profiles/{profile_id}/foundation-runs",
            headers=_headers(csrf, "missing-pack", profile_version),
            json={
                "pack_revision_id": "019fe900-5000-7000-8001-000000000099",
                "foundation_revision_id": str(CATALOGUE.definition.foundation_revision_id),
                "seed": "missing-pack",
            },
        )

    assert missing_precondition.status_code == 428
    assert missing_pack.status_code == 409
    assert missing_pack.json()["code"] == "foundation_pack_missing"


async def test_expired_diagnostic_is_persisted_and_does_not_block_a_new_run(
    foundation_services: tuple[IdentityApplicationService, Any, MutableClock],
) -> None:
    _, _, clock = foundation_services
    async with await _client(foundation_services) as client:
        csrf = await _login(client)
        created = await client.post(
            "/api/v1/language-profiles",
            headers=_headers(csrf, "create-return-profile"),
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        profile_id = created.json()["profile_id"]
        first = await client.post(
            f"/api/v1/language-profiles/{profile_id}/diagnostics",
            headers=_headers(csrf, "start-return-diagnostic-1", 1),
            json={
                "policy_revision_id": POLICY,
                "pack_revision_id": str(CATALOGUE.definition.pack_revision_id),
                "seed": "P-RETOUR-1",
            },
        )
        assert first.status_code == 201
        clock.advance(timedelta(hours=24))
        csrf = await _authenticate(client, "session-return-day-2")
        second = await client.post(
            f"/api/v1/language-profiles/{profile_id}/diagnostics",
            headers=_headers(csrf, "start-return-diagnostic-2", 1),
            json={
                "policy_revision_id": POLICY,
                "pack_revision_id": str(CATALOGUE.definition.pack_revision_id),
                "seed": "P-RETOUR-2",
            },
        )

    assert second.status_code == 201, second.text
    assert second.json()["diagnostic_run_id"] != first.json()["diagnostic_run_id"]
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.connect() as connection:
        old_status = await connection.scalar(
            text(
                "SELECT status FROM language_profiles.diagnostic_runs "
                "WHERE diagnostic_run_id = :run_id"
            ),
            {"run_id": UUID(first.json()["diagnostic_run_id"])},
        )
    await engine.dispose()
    assert old_status == "expired"


async def test_returning_learner_before_twenty_four_hours_resumes_the_same_run(
    foundation_services: tuple[IdentityApplicationService, Any, MutableClock],
) -> None:
    async with await _client(foundation_services) as client:
        csrf = await _login(client)
        created = await client.post(
            "/api/v1/language-profiles",
            headers=_headers(csrf, "create-early-return-profile"),
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        profile_id = created.json()["profile_id"]
        payload = {
            "policy_revision_id": POLICY,
            "pack_revision_id": str(CATALOGUE.definition.pack_revision_id),
            "seed": "P-RETOUR",
        }
        first = await client.post(
            f"/api/v1/language-profiles/{profile_id}/diagnostics",
            headers=_headers(csrf, "start-early-return-1", 1),
            json=payload,
        )
        second = await client.post(
            f"/api/v1/language-profiles/{profile_id}/diagnostics",
            headers=_headers(csrf, "start-early-return-2", 1),
            json=payload,
        )

    assert first.status_code == 201
    assert second.status_code == 201, second.text
    assert second.json() == first.json()
    assert second.headers["etag"] == first.headers["etag"] == '"1"'
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.connect() as connection:
        run_count = await connection.scalar(
            text(
                "SELECT count(*) FROM language_profiles.diagnostic_runs "
                "WHERE profile_id = :profile_id"
            ),
            {"profile_id": UUID(profile_id)},
        )
    await engine.dispose()
    assert run_count == 1


async def test_late_diagnostic_submission_persists_expired_before_returning_error(
    foundation_services: tuple[IdentityApplicationService, Any, MutableClock],
) -> None:
    _, _, clock = foundation_services
    async with await _client(foundation_services) as client:
        csrf = await _login(client)
        created = await client.post(
            "/api/v1/language-profiles",
            headers=_headers(csrf, "create-late-response-profile"),
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        started = await client.post(
            f"/api/v1/language-profiles/{created.json()['profile_id']}/diagnostics",
            headers=_headers(csrf, "start-late-response", 1),
            json={
                "policy_revision_id": POLICY,
                "pack_revision_id": str(CATALOGUE.definition.pack_revision_id),
                "seed": "P-RETOUR",
            },
        )
        clock.advance(timedelta(hours=24))
        csrf = await _authenticate(client, "session-late-response-day-2")
        item = CATALOGUE.definition.blocks[0].items[0]
        late = await client.post(
            f"/api/v1/diagnostics/{started.json()['diagnostic_run_id']}/responses",
            headers=_headers(csrf, "late-diagnostic-response", 1),
            json={
                "item_revision_id": str(item.item_revision_id),
                "ordinal": 1,
                "answer": {"value": item.checker_values[0]},
            },
        )

    assert late.status_code == 409
    assert late.json()["code"] == "run_expired"
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.connect() as connection:
        status_and_version = (
            await connection.execute(
                text(
                    "SELECT status, version FROM language_profiles.diagnostic_runs "
                    "WHERE diagnostic_run_id = :run_id"
                ),
                {"run_id": UUID(started.json()["diagnostic_run_id"])},
            )
        ).one()
    await engine.dispose()
    assert status_and_version.status == "expired"
    assert status_and_version.version == 2


async def test_diagnostic_start_rejects_pack_without_published_foundations(
    foundation_services: tuple[IdentityApplicationService, Any, MutableClock],
) -> None:
    async with await _client(foundation_services) as client:
        csrf = await _login(client)
        created = await client.post(
            "/api/v1/language-profiles",
            headers=_headers(csrf, "create-missing-diagnostic-pack"),
            json={"target_variety_id": TARGET, "native_variety_id": NATIVE},
        )
        response = await client.post(
            f"/api/v1/language-profiles/{created.json()['profile_id']}/diagnostics",
            headers=_headers(csrf, "start-missing-diagnostic-pack", 1),
            json={
                "policy_revision_id": POLICY,
                "pack_revision_id": "019fe900-5000-7000-8001-000000000099",
                "seed": "missing-published-pack",
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "diagnostic_unavailable"
