from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID

from .bindings import _require_uuid7
from .domain import ArcType, LearningModuleRevision
from .ports import ReferenceExpectation, ReferenceManifest, ReferenceStatus, ResolvedReference


class FindingSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFORMATION = "information"


class HumanGateStatus(StrEnum):
    PENDING_HUMAN = "pending_human"
    APPROVED = "approved"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewerRole(StrEnum):
    LINGUIST = "linguist"
    PEDAGOGUE = "pedagogue"


@dataclass(frozen=True, slots=True)
class HumanApprovalEvidence:
    review_id: UUID
    gate_code: str
    reviewer_id: UUID
    reviewer_role: ReviewerRole
    author_id: UUID
    decision: ApprovalDecision
    subject_checksum: str
    fixture_fingerprint: str
    signed_at: datetime
    key_id: str
    signature: bytes

    def __post_init__(self) -> None:
        for field in ("review_id", "reviewer_id", "author_id"):
            _require_uuid7(getattr(self, field), field)

    def signature_payload(self) -> bytes:
        payload = {
            "author_id": str(self.author_id),
            "decision": self.decision.value,
            "fixture_fingerprint": self.fixture_fingerprint,
            "gate_code": self.gate_code,
            "review_id": str(self.review_id),
            "reviewer_id": str(self.reviewer_id),
            "reviewer_role": self.reviewer_role.value,
            "signed_at": self.signed_at.isoformat()
            if isinstance(self.signed_at, datetime)
            else "invalid",
            "subject_checksum": self.subject_checksum,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def coherent_for(
        self,
        *,
        gate_code: str,
        checksum: str,
        fixture_fingerprint: str,
        author_id: UUID,
    ) -> bool:
        required_role = {
            "P-LING": ReviewerRole.LINGUIST,
            "P-PED": ReviewerRole.PEDAGOGUE,
        }.get(gate_code)
        return (
            self.gate_code == gate_code
            and self.reviewer_role is required_role
            and self.decision is ApprovalDecision.APPROVED
            and self.subject_checksum == checksum
            and self.fixture_fingerprint == fixture_fingerprint
            and self.author_id == author_id
            and self.reviewer_id != author_id
            and isinstance(self.signed_at, datetime)
            and self.signed_at.tzinfo is not None
            and self.signed_at.utcoffset() is not None
            and self.signed_at.isoformat() != ""
            and self.key_id != ""
            and self.signature != b""
        )


class HumanApprovalVerifier(Protocol):
    def verify(self, evidence: HumanApprovalEvidence) -> bool: ...


@dataclass(frozen=True, slots=True)
class HumanReviewGate:
    gate_code: str
    status: HumanGateStatus
    approval_evidence: HumanApprovalEvidence | None = None


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
    reference_expectations: tuple[ReferenceExpectation, ...]
    reference_manifest: ReferenceManifest
    grammar_explanations: tuple[tuple[int, str], ...]
    grammar_practices: tuple[tuple[int, str, str], ...]
    morphology_oracles: tuple[MorphologyOracle, ...]
    pronunciation_oracles: tuple[PronunciationOracle, ...]
    profile_novelty_limits: tuple[tuple[str, float], ...]
    day_novelty_points: tuple[tuple[int, float], ...]
    human_gates: tuple[HumanReviewGate | tuple[str, HumanGateStatus], ...]
    module_author_id: UUID | None = None
    fixture_fingerprint: str = ""
    approval_verifier: HumanApprovalVerifier | None = None

    def __post_init__(self) -> None:
        for field in (
            "resolved_references",
            "reference_expectations",
            "grammar_explanations",
            "grammar_practices",
            "morphology_oracles",
            "pronunciation_oracles",
            "profile_novelty_limits",
            "day_novelty_points",
        ):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        gates = tuple(
            item if isinstance(item, HumanReviewGate) else HumanReviewGate(*item)
            for item in self.human_gates
        )
        object.__setattr__(self, "human_gates", gates)


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
    expectations = {item.reference: item for item in data.reference_manifest.entries}
    findings: list[ValidationFinding] = []
    manifest_mismatch = (
        data.reference_manifest.checksum != data.module.reference_manifest_checksum
    )
    for reference in sorted(expected):
        item = resolved.get(reference)
        expectation = expectations.get(reference)
        path = f"references.{reference}"
        if expectation is None:
            findings.append(_finding("module_target_unresolved", path, reference))
            continue
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
        if item.kind != expectation.kind:
            manifest_mismatch = True
            findings.append(_finding("module_reference_kind_mismatch", path, reference))
        if item.pack_revision_id != expectation.pack_revision_id:
            manifest_mismatch = True
            findings.append(_finding("module_reference_pack_mismatch", path, reference))
        if item.variety_id != expectation.variety_id:
            manifest_mismatch = True
            findings.append(_finding("module_reference_variety_mismatch", path, reference))
        if item.checksum != expectation.checksum:
            manifest_mismatch = True
            findings.append(_finding("module_reference_checksum_mismatch", path, reference))
    if len(expectations) != len(data.reference_manifest.entries) or set(expectations) != expected:
        findings.append(_finding("module_target_unresolved", "reference_expectations"))
        manifest_mismatch = True
    if manifest_mismatch:
        findings.append(
            _finding("module_reference_manifest_mismatch", "reference_manifest")
        )
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


def _graph_findings(data: ValidationInput) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    bound_explanations: list[tuple[int, str]] = []
    bound_practices: list[tuple[int, str, str]] = []
    bound_morphology: set[str] = set()
    bound_pronunciation: set[str] = set()
    for day in data.module.days:
        path = f"days.{day.ordinal}"
        required_parts = (
            day.context_revision_ids,
            day.skill_bindings,
            day.lexicon_bindings,
            day.grammar_bindings,
            day.exercise_bindings,
            day.fallback_revision_ids,
            day.validator_revision_ids,
        )
        if any(not part for part in required_parts) or not day.final_output_spec:
            findings.append(_finding("module_day_graph_incomplete", path))
        if day.ordinal > 1 and not day.recall_specs:
            findings.append(_finding("module_day_graph_incomplete", f"{path}.recall"))

        grammar_families = {binding.family_code for binding in day.grammar_bindings}
        if grammar_families != set(day.explained_grammar_family_codes):
            findings.append(_finding("module_validation_input_unbound", f"{path}.grammar"))
        if not set(day.gym_grammar_family_codes).issubset(grammar_families):
            findings.append(_finding("module_validation_input_unbound", f"{path}.gym"))
        for binding in day.grammar_bindings:
            bound_explanations.append((day.ordinal, binding.family_code))
            bound_practices.extend(
                (day.ordinal, binding.family_code, operation)
                for operation in binding.allowed_operations
            )
        bound_morphology.update(
            f"analysis:{binding.form_analysis_id}" for binding in day.morphology_bindings
        )
        bound_pronunciation.update(
            f"pronunciation:{binding.target_revision_id}"
            for binding in day.pronunciation_bindings
        )
        target_universe = set(day.primary_target_refs) | set(day.secondary_target_refs)
        primary_skill_targets = {
            target for target in day.primary_target_refs if target.startswith("skill:")
        }
        bound_primary_skills = {
            binding.target_ref
            for binding in day.skill_bindings
            if binding.credit_eligible and binding.target_ref
        }
        if not primary_skill_targets.issubset(bound_primary_skills):
            findings.append(_finding("module_target_uncovered", f"{path}.skills"))
        for exercise in day.exercise_bindings:
            if not set(exercise.target_bindings).issubset(target_universe):
                findings.append(
                    _finding("module_target_uncovered", f"{path}.exercises")
                )
            if exercise.gym_operation is not None:
                matching_grammar = tuple(
                    binding
                    for binding in day.grammar_bindings
                    if f"grammar:{binding.family_code}" in exercise.target_bindings
                )
                if not matching_grammar or not any(
                    exercise.gym_operation in binding.allowed_operations
                    for binding in matching_grammar
                ):
                    findings.append(
                        _finding("module_validation_input_unbound", f"{path}.gym")
                    )
        if day.novelty_budget == 0 and any(
            binding.role.value == "new"
            for bindings in (
                day.skill_bindings,
                day.lexicon_bindings,
                day.grammar_bindings,
                day.morphology_bindings,
                day.pronunciation_bindings,
            )
            for binding in bindings
        ):
            findings.append(
                _finding("module_novelty_budget_exceeded", f"{path}.bindings")
            )
        for recall in day.recall_specs:
            source_day = next(
                (
                    candidate
                    for candidate in data.module.days
                    if candidate.ordinal == recall.source_day_ordinal
                ),
                None,
            )
            if (
                source_day is None
                or (
                    recall.due_rule == "j+1"
                    and recall.source_day_ordinal != day.ordinal - 1
                )
                or recall.target_ref
                not in set(source_day.primary_target_refs)
                | set(source_day.secondary_target_refs)
                or recall.source_exercise_binding_id
                not in {
                    exercise.definition_revision_id
                    for exercise in source_day.exercise_bindings
                }
            ):
                findings.append(
                    _finding("module_recall_source_missing", f"{path}.recall")
                )
    if (
        tuple(sorted(bound_explanations)) != tuple(sorted(data.grammar_explanations))
        or tuple(sorted(bound_practices)) != tuple(sorted(data.grammar_practices))
        or len(bound_explanations) != len(data.grammar_explanations)
        or len(bound_practices) != len(data.grammar_practices)
    ):
        findings.append(_finding("module_validation_input_unbound", "grammar"))
    if bound_morphology != {item.target_ref for item in data.morphology_oracles}:
        findings.append(_finding("module_validation_input_unbound", "morphology"))
    if bound_pronunciation != {item.target_ref for item in data.pronunciation_oracles}:
        findings.append(_finding("module_validation_input_unbound", "pronunciation"))
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
            not math.isfinite(points)
            or points < 0
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
    findings.extend(_graph_findings(data))
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
    gates = tuple(cast(HumanReviewGate, item) for item in data.human_gates)
    required_gate_codes = {"P-LING", "P-PED"}
    gate_codes = [item.gate_code for item in gates]
    for missing in sorted(required_gate_codes - set(gate_codes)):
        findings.append(
            _finding("module_human_gate_missing", f"human_gates.{missing}", missing)
        )
    for unknown in sorted(set(gate_codes) - required_gate_codes):
        findings.append(
            _finding("module_human_gate_unknown", f"human_gates.{unknown}", unknown)
        )
    for duplicate in sorted({code for code in gate_codes if gate_codes.count(code) > 1}):
        findings.append(
            _finding(
                "module_human_gate_duplicate",
                f"human_gates.{duplicate}",
                duplicate,
            )
        )
    for gate in gates:
        if gate.gate_code not in required_gate_codes:
            continue
        evidence = gate.approval_evidence
        evidence_valid = (
            gate.status is HumanGateStatus.APPROVED
            and evidence is not None
            and data.module_author_id is not None
            and data.fixture_fingerprint.startswith("sha256:")
            and len(data.fixture_fingerprint) == 71
            and data.approval_verifier is not None
            and evidence.coherent_for(
                gate_code=gate.gate_code,
                checksum=data.module.payload_checksum,
                fixture_fingerprint=data.fixture_fingerprint,
                author_id=data.module_author_id,
            )
            and data.approval_verifier.verify(evidence)
        )
        if gate.status is HumanGateStatus.APPROVED and not evidence_valid:
            findings.append(
                _finding(
                    "module_human_approval_evidence_invalid",
                    f"human_gates.{gate.gate_code}",
                    gate.gate_code,
                )
            )
        if not evidence_valid:
            findings.append(
                _finding(
                    "module_human_review_required",
                    f"human_gates.{gate.gate_code}",
                    gate.gate_code,
                )
            )
    return ValidationReport(
        tuple(sorted(set(findings), key=lambda item: item.sort_key)),
        data.module.payload_checksum,
        tuple(sorted(credit_eligible)),
    )
