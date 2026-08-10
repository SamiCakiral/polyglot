from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .domain import ArcType, LearningModuleRevision
from .ports import ReferenceStatus, ResolvedReference


class FindingSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFORMATION = "information"


class HumanGateStatus(StrEnum):
    PENDING_HUMAN = "pending_human"
    APPROVED = "approved"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    validator_code: str
    severity: FindingSeverity
    path: str
    message_code: str
    references: tuple[str, ...] = ()

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.severity.value, self.path, self.message_code)


@dataclass(frozen=True, slots=True)
class MorphologyOracle:
    target_ref: str
    feature_bundle: tuple[tuple[str, str], ...]
    accepted_surface: str
    oracle_available: bool


@dataclass(frozen=True, slots=True)
class PronunciationOracle:
    target_ref: str
    transcript: str
    transcript_checksum: str
    media_transcript_checksum: str
    evaluability: str


@dataclass(frozen=True, slots=True)
class ValidationInput:
    module: LearningModuleRevision
    resolved_references: tuple[ResolvedReference, ...]
    grammar_explanations: tuple[tuple[int, str], ...]
    grammar_practices: tuple[tuple[int, str, str], ...]
    morphology_oracles: tuple[MorphologyOracle, ...]
    pronunciation_oracles: tuple[PronunciationOracle, ...]
    profile_novelty_limits: tuple[tuple[str, float], ...]
    day_novelty_points: tuple[tuple[int, float], ...]
    human_gates: tuple[tuple[str, HumanGateStatus], ...]

    def __post_init__(self) -> None:
        for field in (
            "resolved_references",
            "grammar_explanations",
            "grammar_practices",
            "morphology_oracles",
            "pronunciation_oracles",
            "profile_novelty_limits",
            "day_novelty_points",
            "human_gates",
        ):
            object.__setattr__(self, field, tuple(getattr(self, field)))


@dataclass(frozen=True, slots=True)
class ValidationReport:
    findings: tuple[ValidationFinding, ...]
    payload_checksum: str
    credit_eligible_pronunciation_refs: tuple[str, ...]

    @property
    def blocking(self) -> bool:
        return any(item.severity is FindingSeverity.BLOCKING for item in self.findings)


def _finding(
    code: str,
    path: str,
    *references: str,
    severity: FindingSeverity = FindingSeverity.BLOCKING,
) -> ValidationFinding:
    return ValidationFinding("W11-CURRICULUM-V1", severity, path, code, tuple(references))


def _reference_findings(data: ValidationInput) -> list[ValidationFinding]:
    expected = set(data.module.all_reference_keys())
    resolved = {item.reference: item for item in data.resolved_references}
    findings: list[ValidationFinding] = []
    for reference in sorted(expected):
        item = resolved.get(reference)
        path = f"references.{reference}"
        if item is None or item.status in {ReferenceStatus.MISSING, ReferenceStatus.FORBIDDEN}:
            findings.append(_finding("module_target_unresolved", path, reference))
            continue
        if item.status is ReferenceStatus.RETIRED:
            findings.append(_finding("module_reference_retired_for_new_use", path, reference))
        elif item.status is not ReferenceStatus.PUBLISHED:
            findings.append(_finding("module_reference_not_published", path, reference))
        if not item.provenance_id:
            findings.append(_finding("module_provenance_missing", path, reference))
        if not item.rights_refs:
            findings.append(_finding("module_rights_missing", path, reference))
    return findings


def _grammar_findings(data: ValidationInput) -> list[ValidationFinding]:
    explained_at: dict[str, int] = {}
    for ordinal, family in data.grammar_explanations:
        explained_at[family] = min(ordinal, explained_at.get(family, ordinal))
    findings: list[ValidationFinding] = []
    for ordinal, family, operation in data.grammar_practices:
        if family not in explained_at or explained_at[family] > ordinal:
            findings.append(
                _finding(
                    "module_new_structure_without_explanation", f"days.{ordinal}.grammar", family
                )
            )
        prefix, _, number = operation.partition("-")
        if prefix != "GYM" or not number.isdigit() or not 1 <= int(number) <= 15:
            findings.append(
                _finding("module_gym_without_w10_contract", f"days.{ordinal}.gym", operation)
            )
    return findings


def _load_findings(data: ValidationInput) -> list[ValidationFinding]:
    day_by_ordinal = {item.ordinal: item for item in data.module.days}
    findings: list[ValidationFinding] = []
    novelty_ordinals = tuple(ordinal for ordinal, _ in data.day_novelty_points)
    expected_ordinals = tuple(item.ordinal for item in data.module.days)
    if tuple(sorted(novelty_ordinals)) != expected_ordinals:
        findings.append(
            _finding("module_load_budget_exceeded", "day_novelty_points")
        )
    for ordinal, points in data.day_novelty_points:
        day = day_by_ordinal.get(ordinal)
        if day is None:
            findings.append(_finding("module_day_ordinal_gap", f"days.{ordinal}"))
            continue
        if (
            points < 0
            or points > day.novelty_budget
            or (day.arc_type in {ArcType.TRANSFER, ArcType.CONSOLIDATION} and points > 0)
        ):
            findings.append(_finding("module_novelty_budget_exceeded", f"days.{ordinal}.novelty"))
    limits = dict(data.profile_novelty_limits)
    total = sum(points for _, points in data.day_novelty_points)
    for profile in data.module.entry_profile_codes:
        if profile not in limits or total > limits[profile] * data.module.nominal_days:
            findings.append(_finding("module_load_budget_exceeded", f"profiles.{profile}"))
    return findings


def validate_curriculum(data: ValidationInput) -> ValidationReport:
    findings = _reference_findings(data)
    findings.extend(_grammar_findings(data))
    findings.extend(_load_findings(data))
    for morphology in data.morphology_oracles:
        if (
            not morphology.oracle_available
            or not morphology.feature_bundle
            or not morphology.accepted_surface
        ):
            findings.append(
                _finding(
                    "module_morphology_oracle_missing",
                    f"morphology.{morphology.target_ref}",
                )
            )
    credit_eligible: list[str] = []
    for pronunciation in data.pronunciation_oracles:
        path = f"pronunciation.{pronunciation.target_ref}"
        if (
            not pronunciation.transcript
            or pronunciation.transcript_checksum != pronunciation.media_transcript_checksum
        ):
            findings.append(_finding("module_pronunciation_asset_incoherent", path))
        if pronunciation.evaluability != "perception":
            findings.append(
                _finding(
                    "module_pronunciation_not_evaluable",
                    path,
                    severity=FindingSeverity.INFORMATION,
                )
            )
        else:
            credit_eligible.append(pronunciation.target_ref)
    for gate, status in data.human_gates:
        if status is not HumanGateStatus.APPROVED:
            findings.append(_finding("module_human_review_required", f"human_gates.{gate}", gate))
    return ValidationReport(
        tuple(sorted(set(findings), key=lambda item: item.sort_key)),
        data.module.payload_checksum,
        tuple(sorted(credit_eligible)),
    )
