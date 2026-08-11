# ruff: noqa: E501

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.progress.domain import (
    MasteryProjection,
    MasteryStatus,
    Modality,
    ModalityProjection,
    project_modality,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class MasteryFacetView:
    target_type: str
    target_id: str
    facet_key: str
    modality: str
    operation: str
    status: str
    mastery_base: float
    mastery_current: float
    confidence: float
    freshness: float
    effective_mass: float
    success_count: int
    failure_count: int
    context_count: int
    session_count: int
    delay_band_count: int
    transfer_count: int
    last_evidence_at: datetime | None
    next_verification_at: datetime | None
    policy_revision: str
    projection_version: int
    evidence_ids: tuple[UUID, ...]
    ineligibility_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModalityProgressView:
    modality: str
    status: str
    score: float | None
    confidence: float
    freshness: float | None
    coverage: float
    observed_facet_count: int
    expected_facet_count: int
    assessment_status: str | None = None
    assessment_score: float | None = None
    assessment_band: str | None = None
    assessment_confidence: float | None = None
    assessment_completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProgressOverviewView:
    profile_id: UUID
    modalities: tuple[ModalityProgressView, ...]
    facets: tuple[MasteryFacetView, ...]
    next_cursor: str | None
    policy_revision: str
    has_global_score: bool = False


@dataclass(frozen=True, slots=True)
class RecommendationView:
    recommendation_id: UUID
    target_type: str
    target_id: str
    facet_key: str
    need_id: UUID | None
    reason_code: str
    reason_params: dict[str, JsonValue]
    missing_evidence_spec: dict[str, JsonValue]
    proposed_activity: dict[str, JsonValue]
    priority: float
    urgency: float
    estimated_duration_ms: int
    policy_revision: str
    authorized_fact_ids: tuple[UUID, ...]
    created_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecommendationPageView:
    profile_id: UUID
    items: tuple[RecommendationView, ...]
    next_cursor: str | None


def _cursor_encode(values: tuple[str, ...]) -> str:
    raw = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _cursor_decode(value: str | None, *, size: int) -> tuple[str, ...] | None:
    if value is None:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as error:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid cursor") from error
    if (
        not isinstance(decoded, list)
        or len(decoded) != size
        or not all(isinstance(item, str) for item in decoded)
    ):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid cursor")
    return tuple(decoded)


def _projection_from_row(row: dict[str, object]) -> MasteryProjection:
    return MasteryProjection(
        status=MasteryStatus(str(row["status"])),
        modality=Modality(str(row["modality"])),
        mastery_base=float(str(row["mastery_base"])),
        mastery_current=float(str(row["mastery_current"])),
        confidence=float(str(row["confidence"])),
        freshness=float(str(row["freshness"])),
        effective_mass=float(str(row["effective_mass"])),
        success_count=int(str(row["success_count"])),
        failure_count=int(str(row["failure_count"])),
        context_count=int(str(row["context_count"])),
        session_count=int(str(row["session_count"])),
        delay_band_count=int(str(row["delay_band_count"])),
        transfer_count=int(str(row["transfer_count"])),
        evidence_ids=(),
        last_evidence_at=cast(datetime | None, row["last_evidence_at"]),
        next_verification_at=cast(datetime | None, row["next_verification_at"]),
        policy_revision_id="MASTERY_V0",
    )


class SqlProgressQueryService:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get_overview(
        self,
        actor_id: UUID,
        profile_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> ProgressOverviewView:
        if not 1 <= limit <= 100:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        after = _cursor_decode(cursor, size=5)
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._require_profile(session, profile_id)
            all_rows = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM progress.mastery_projections WHERE profile_id=:profile "
                            "ORDER BY target_type,target_id,facet_key,modality,operation"
                        ),
                        {"profile": profile_id},
                    )
                )
                .mappings()
                .all()
            )
            expected = {
                str(row[0]): int(row[1])
                for row in (
                    await session.execute(
                        text(
                            "SELECT skill.modality,count(*) FROM catalogue.skill_revisions skill "
                            "JOIN catalogue.language_pack_revisions pack "
                            "ON pack.pack_revision_id=skill.pack_revision_id "
                            "JOIN language_profiles.learner_language_profiles profile "
                            "ON profile.target_variety_id=pack.target_variety_id "
                            "WHERE profile.profile_id=:profile AND skill.status='published' "
                            "AND pack.status='published' GROUP BY skill.modality"
                        ),
                        {"profile": profile_id},
                    )
                ).all()
            }
            assessment_rows = (
                (
                    await session.execute(
                        text(
                            "SELECT DISTINCT ON (modality) modality,result_status,score,band,"
                            "confidence,created_at FROM assessments.assessment_results "
                            "WHERE profile_id=:profile "
                            "ORDER BY modality,created_at DESC,result_id DESC"
                        ),
                        {"profile": profile_id},
                    )
                )
                .mappings()
                .all()
            )
            assessments = {str(row["modality"]): dict(row) for row in assessment_rows}
            page_rows = [dict(row) for row in all_rows]
            if after is not None:
                page_rows = [
                    row
                    for row in page_rows
                    if (
                        str(row["target_type"]),
                        str(row["target_id"]),
                        str(row["facet_key"]),
                        str(row["modality"]),
                        str(row["operation"]),
                    )
                    > after
                ]
            has_more = len(page_rows) > limit
            page_rows = page_rows[:limit]
            facets = tuple([await self._facet_view(session, profile_id, row) for row in page_rows])
            modality_views: list[ModalityProgressView] = []
            for modality in Modality:
                weighted = tuple(
                    (_projection_from_row(dict(row)), 1.0)
                    for row in all_rows
                    if row["modality"] == modality.value
                )
                eligible_weight = float(max(expected.get(modality.value, 0), len(weighted)))
                summary = project_modality(
                    modality,
                    weighted,
                    eligible_weight=eligible_weight,
                )
                modality_views.append(
                    self._modality_view(
                        summary,
                        expected_count=int(eligible_weight),
                        assessment=assessments.get(modality.value),
                    )
                )
            next_cursor = None
            if has_more and page_rows:
                last = page_rows[-1]
                next_cursor = _cursor_encode(
                    (
                        str(last["target_type"]),
                        str(last["target_id"]),
                        str(last["facet_key"]),
                        str(last["modality"]),
                        str(last["operation"]),
                    )
                )
            return ProgressOverviewView(
                profile_id,
                tuple(modality_views),
                facets,
                next_cursor,
                "MASTERY_V0",
            )

    async def list_recommendations(
        self,
        actor_id: UUID,
        profile_id: UUID,
        *,
        cursor: str | None,
        limit: int,
        as_of: datetime,
    ) -> RecommendationPageView:
        if not 1 <= limit <= 100:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        after = _cursor_decode(cursor, size=2)
        parameters: dict[str, object] = {
            "profile": profile_id,
            "as_of": as_of,
            "limit": limit + 1,
        }
        cursor_clause = ""
        if after is not None:
            cursor_clause = (
                "AND (priority,recommendation_id)<(:priority,CAST(:recommendation AS uuid)) "
            )
            parameters.update({"priority": float(after[0]), "recommendation": after[1]})
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._require_profile(session, profile_id)
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT recommendation.*,policy.policy_code FROM progress.recommendations recommendation "
                            "JOIN progress.policy_revisions policy "
                            "ON policy.policy_revision_id=recommendation.policy_revision_id "
                            "WHERE recommendation.profile_id=:profile AND dismissed_at IS NULL "
                            "AND (expires_at IS NULL OR expires_at>:as_of) "
                            + cursor_clause
                            + "ORDER BY priority DESC,recommendation_id DESC LIMIT :limit"
                        ),
                        parameters,
                    )
                )
                .mappings()
                .all()
            )
            has_more = len(rows) > limit
            rows = rows[:limit]
            items = []
            for row in rows:
                facts = (
                    tuple(
                        (
                            await session.execute(
                                text(
                                    "SELECT source_fact_id FROM progress.learning_need_causes "
                                    "WHERE need_id=:need ORDER BY opened_at,cause_id LIMIT 100"
                                ),
                                {"need": row["need_id"]},
                            )
                        ).scalars()
                    )
                    if row["need_id"] is not None
                    else ()
                )
                items.append(
                    RecommendationView(
                        recommendation_id=UUID(str(row["recommendation_id"])),
                        target_type=str(row["target_type"]),
                        target_id=str(row["target_id"]),
                        facet_key=str(row["facet_key"]),
                        need_id=UUID(str(row["need_id"])) if row["need_id"] else None,
                        reason_code=str(row["reason_code"]),
                        reason_params=cast(dict[str, JsonValue], row["reason_params"]),
                        missing_evidence_spec=cast(
                            dict[str, JsonValue], row["missing_evidence_spec"]
                        ),
                        proposed_activity=cast(dict[str, JsonValue], row["proposed_activity"]),
                        priority=float(str(row["priority"])),
                        urgency=float(str(row["urgency"])),
                        estimated_duration_ms=int(str(row["estimated_duration_ms"])),
                        policy_revision=str(row["policy_code"]),
                        authorized_fact_ids=tuple(UUID(str(value)) for value in facts),
                        created_at=cast(datetime, row["created_at"]),
                        expires_at=cast(datetime | None, row["expires_at"]),
                    )
                )
            next_cursor = None
            if has_more and rows:
                last = rows[-1]
                next_cursor = _cursor_encode(
                    (str(last["priority"]), str(last["recommendation_id"]))
                )
            return RecommendationPageView(profile_id, tuple(items), next_cursor)

    async def _facet_view(
        self,
        session: AsyncSession,
        profile_id: UUID,
        row: dict[str, object],
    ) -> MasteryFacetView:
        evidence_rows = (
            (
                await session.execute(
                    text(
                        "SELECT evidence_id,ineligibility_reasons FROM progress.learning_evidence "
                        "WHERE profile_id=:profile AND target_type=:target_type AND target_id=:target "
                        "AND facet_key=:facet AND modality=:modality AND operation=:operation "
                        "ORDER BY created_at DESC,evidence_id DESC LIMIT 100"
                    ),
                    {
                        "profile": profile_id,
                        "target_type": row["target_type"],
                        "target": row["target_id"],
                        "facet": row["facet_key"],
                        "modality": row["modality"],
                        "operation": row["operation"],
                    },
                )
            )
            .mappings()
            .all()
        )
        reasons = sorted(
            {str(reason) for item in evidence_rows for reason in item["ineligibility_reasons"]}
        )
        return MasteryFacetView(
            target_type=str(row["target_type"]),
            target_id=str(row["target_id"]),
            facet_key=str(row["facet_key"]),
            modality=str(row["modality"]),
            operation=str(row["operation"]),
            status=str(row["status"]),
            mastery_base=float(str(row["mastery_base"])),
            mastery_current=float(str(row["mastery_current"])),
            confidence=float(str(row["confidence"])),
            freshness=float(str(row["freshness"])),
            effective_mass=float(str(row["effective_mass"])),
            success_count=int(str(row["success_count"])),
            failure_count=int(str(row["failure_count"])),
            context_count=int(str(row["context_count"])),
            session_count=int(str(row["session_count"])),
            delay_band_count=int(str(row["delay_band_count"])),
            transfer_count=int(str(row["transfer_count"])),
            last_evidence_at=cast(datetime | None, row["last_evidence_at"]),
            next_verification_at=cast(datetime | None, row["next_verification_at"]),
            policy_revision="MASTERY_V0",
            projection_version=int(str(row["projection_version"])),
            evidence_ids=tuple(UUID(str(item["evidence_id"])) for item in evidence_rows),
            ineligibility_reasons=tuple(reasons),
        )

    @staticmethod
    def _modality_view(
        projection: ModalityProjection,
        *,
        expected_count: int,
        assessment: dict[str, object] | None = None,
    ) -> ModalityProgressView:
        return ModalityProgressView(
            modality=projection.modality.value,
            status=projection.status.value,
            score=projection.score,
            confidence=projection.confidence,
            freshness=projection.freshness,
            coverage=projection.coverage,
            observed_facet_count=projection.observed_facet_count,
            expected_facet_count=expected_count,
            assessment_status=(
                str(assessment["result_status"]) if assessment else None
            ),
            assessment_score=(
                float(str(assessment["score"]))
                if assessment and assessment["score"] is not None
                else None
            ),
            assessment_band=(
                str(assessment["band"])
                if assessment and assessment["band"] is not None
                else None
            ),
            assessment_confidence=(
                float(str(assessment["confidence"])) if assessment else None
            ),
            assessment_completed_at=(
                cast(datetime, assessment["created_at"]) if assessment else None
            ),
        )

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(actor_id)},
        )

    @staticmethod
    async def _require_profile(session: AsyncSession, profile_id: UUID) -> None:
        exists = await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles "
                "WHERE profile_id=:profile AND status<>'deleted')"
            ),
            {"profile": profile_id},
        )
        if not exists:
            raise DomainError(ErrorCode.NOT_FOUND)
