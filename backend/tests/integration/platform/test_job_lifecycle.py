from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.ids import Uuid7Generator


def new_id() -> object:
    return Uuid7Generator().new()


async def insert_queued_job(session: AsyncSession) -> object:
    from polyglot.platform.persistence.models import jobs

    now = datetime.now(UTC)
    job_id = new_id()
    await session.execute(
        jobs.insert().values(
            job_id=job_id,
            job_type="fixture_operation",
            requested_by_actor_id=new_id(),
            profile_id=None,
            status="queued",
            idempotency_key=f"job-{job_id}",
            request_fingerprint="a" * 64,
            correlation_id=new_id(),
            payload_schema_version=1,
            requested_at=now,
            queued_at=now,
            started_at=None,
            finished_at=None,
            cancel_requested_at=None,
            retry_not_before_at=None,
            progress_completed=0,
            progress_total=1,
            result_ref=None,
            error_code=None,
            version=1,
        )
    )
    await session.commit()
    return job_id


async def test_job_claim_renews_expires_and_fences_stale_completion(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.models import job_attempts, jobs
    from polyglot.platform.persistence.repositories import SqlJobStore

    job_id = await insert_queued_job(session)
    store = SqlJobStore(session)
    started_at = datetime.now(UTC)
    first = await store.claim(
        job_id=job_id,
        worker_id="worker-a",
        now=started_at,
        lease_for=timedelta(minutes=5),
    )
    assert first is not None
    assert await store.renew(
        claim=first,
        now=started_at + timedelta(minutes=1),
        lease_for=timedelta(minutes=5),
    )
    assert await store.claim(
        job_id=job_id,
        worker_id="worker-b",
        now=started_at + timedelta(minutes=2),
        lease_for=timedelta(minutes=5),
    ) is None

    replacement = await store.claim(
        job_id=job_id,
        worker_id="worker-b",
        now=started_at + timedelta(minutes=7),
        lease_for=timedelta(minutes=5),
    )
    assert replacement is not None
    assert replacement.attempt_no == first.attempt_no
    assert replacement.lease_token != first.lease_token
    assert not await store.succeed(
        claim=first,
        finished_at=started_at + timedelta(minutes=7),
        result_ref=new_id(),
    )
    assert await store.succeed(
        claim=replacement,
        finished_at=started_at + timedelta(minutes=8),
        result_ref=new_id(),
    )
    await session.commit()

    assert await session.scalar(select(jobs.c.status).where(jobs.c.job_id == job_id)) == "succeeded"
    facts = (
        await session.execute(select(job_attempts).where(job_attempts.c.job_id == job_id))
    ).mappings().all()
    assert len(facts) == 1
    assert facts[0]["status"] == "succeeded"
    assert "lease_owner" not in facts[0]
    assert "lease_expires_at" not in facts[0]


async def test_retryable_failure_waits_then_appends_a_new_terminal_attempt(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.models import job_attempts, jobs
    from polyglot.platform.persistence.repositories import SqlJobStore

    job_id = await insert_queued_job(session)
    store = SqlJobStore(session)
    started_at = datetime.now(UTC)
    first = await store.claim(
        job_id=job_id,
        worker_id="worker-a",
        now=started_at,
        lease_for=timedelta(minutes=5),
    )
    assert first is not None
    retry_at = started_at + timedelta(minutes=10)
    assert await store.fail(
        claim=first,
        finished_at=started_at + timedelta(minutes=1),
        error_code="provider_unavailable",
        retry_not_before_at=retry_at,
    )
    await session.commit()

    job_status = await session.scalar(select(jobs.c.status).where(jobs.c.job_id == job_id))
    assert job_status == "retry_wait"
    assert await store.claim(
        job_id=job_id,
        worker_id="worker-b",
        now=retry_at - timedelta(seconds=1),
        lease_for=timedelta(minutes=5),
    ) is None
    second = await store.claim(
        job_id=job_id,
        worker_id="worker-b",
        now=retry_at,
        lease_for=timedelta(minutes=5),
    )
    assert second is not None
    assert second.attempt_no == 2
    assert await store.fail(
        claim=second,
        finished_at=retry_at + timedelta(minutes=1),
        error_code="validation_failed",
        retry_not_before_at=None,
    )
    await session.commit()

    statuses = list(
        (
            await session.execute(
                select(job_attempts.c.status)
                .where(job_attempts.c.job_id == job_id)
                .order_by(job_attempts.c.attempt_no)
            )
        ).scalars()
    )
    assert statuses == ["retryable_failed", "failed"]
    assert await session.scalar(select(jobs.c.status).where(jobs.c.job_id == job_id)) == "failed"


@pytest.mark.parametrize("terminal_action", ["succeed", "fail"])
async def test_job_terminal_action_rejects_expired_lease_with_backdated_timestamp(
    session: AsyncSession,
    terminal_action: str,
) -> None:
    from polyglot.platform.persistence.models import job_attempts, job_claims, jobs
    from polyglot.platform.persistence.repositories import SqlJobStore

    job_id = await insert_queued_job(session)
    store = SqlJobStore(session)
    claimed_at = datetime.now(UTC)
    claim = await store.claim(
        job_id=job_id,
        worker_id="late-worker",
        now=claimed_at,
        lease_for=timedelta(minutes=5),
    )
    assert claim is not None
    await session.execute(
        job_claims.update()
        .where(job_claims.c.job_id == job_id)
        .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
    )

    if terminal_action == "succeed":
        accepted = await store.succeed(
            claim=claim,
            finished_at=claimed_at - timedelta(days=1),
            result_ref=new_id(),
        )
    else:
        accepted = await store.fail(
            claim=claim,
            finished_at=claimed_at - timedelta(days=1),
            error_code="late_failure",
            retry_not_before_at=None,
        )

    assert not accepted
    assert await session.scalar(
        select(func.count()).select_from(job_attempts).where(job_attempts.c.job_id == job_id)
    ) == 0
    assert await session.scalar(select(jobs.c.status).where(jobs.c.job_id == job_id)) == "running"
    assert await session.scalar(
        select(job_claims.c.lease_token).where(job_claims.c.job_id == job_id)
    ) == claim.lease_token
