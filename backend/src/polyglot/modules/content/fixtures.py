import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.json_types import JsonValue


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _ManifestData(_StrictModel):
    id: str
    kind: Literal["positive", "negative"]
    expected_status: Literal["accepted", "rejected"]
    expected_error: str | None = None


class _MetadataData(_StrictModel):
    schema_version: Literal[1]
    synthetic: Literal[True]
    seed: int
    clock: datetime
    payloads: dict[str, str]
    oracles: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    linguistic_review: Literal["pending_human"]


class ProvenanceFixture(_StrictModel):
    provenance_id: UUID
    source_type: Literal["fixture", "human_author", "import", "tool"]
    source_ref: str


class ActorFixture(_StrictModel):
    actor_id: UUID
    roles: tuple[Literal["author", "reviewer", "admin"], ...]


class RevisionFixture(_StrictModel):
    content_revision_id: UUID
    content_id: UUID
    revision_no: int
    status: Literal[
        "draft",
        "validating",
        "validated",
        "approved",
        "published",
        "retired",
        "superseded",
        "rejected",
        "abandoned",
    ]
    payload: dict[str, JsonValue]
    payload_checksum: str
    provenance_id: UUID
    rights_ref: str
    author_id: UUID
    reviewer_id: UUID | None = None


class ValidationOracle(_StrictModel):
    validation_status: Literal["passed", "failed", "human_required"]
    resulting_revision_status: Literal["validated", "draft"]


class ReviewDecisionFixture(_StrictModel):
    decision_id: UUID
    content_revision_id: UUID
    author_id: UUID
    reviewer_id: UUID
    decision: Literal["approved", "rejected"]
    reason_code: str


class NegativeOracle(_StrictModel):
    case: str
    expected_error: str


class LinguisticOracle(_StrictModel):
    case: str
    document_ref: Literal["docs/v2/22-imports-edition-validation.md#8"]
    expected_outcome: Literal["human_required"]


class HistoricalReferenceFixture(_StrictModel):
    reference_id: UUID
    content_revision_id: UUID
    usage_type: str
    usage_ref: str
    context_checksum: str


class _ReferenceFixture(_StrictModel):
    reference_kind: str
    revision_id: UUID
    status: Literal["published"]


class _PublicationFixture(_StrictModel):
    content_revision_id: UUID
    provenance_id: UUID
    references: tuple[_ReferenceFixture, ...]
    checksum: str


class _ContentPayload(_StrictModel):
    schema_version: Literal[1]
    fixture_id: str
    synthetic: Literal[True]
    linguistic_review: Literal["pending_human"]
    actors: tuple[ActorFixture, ...]
    provenance: tuple[ProvenanceFixture, ...]
    revisions: tuple[RevisionFixture, ...]
    validation_oracles: tuple[ValidationOracle, ...]
    review_decisions: tuple[ReviewDecisionFixture, ...]
    negative_oracles: tuple[NegativeOracle, ...]
    linguistic_oracles: tuple[LinguisticOracle, ...]
    historical_references: tuple[HistoricalReferenceFixture, ...]
    publication_manifest: _PublicationFixture


class _MutationData(_StrictModel):
    kind: Literal[
        "invalid-checksum",
        "invalid-provenance",
        "invalid-rights",
        "corrupt-manifest",
    ]


@dataclass(frozen=True, slots=True)
class ContentFixtureManifestVerification:
    fixture_id: str
    payload_names: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    linguistic_review: str


@dataclass(frozen=True, slots=True)
class ContentFixture:
    synthetic: bool
    linguistic_review: str
    actors: tuple[ActorFixture, ...]
    provenance: tuple[ProvenanceFixture, ...]
    revisions: tuple[RevisionFixture, ...]
    validation_oracles: tuple[ValidationOracle, ...]
    review_decisions: tuple[ReviewDecisionFixture, ...]
    negative_oracles: tuple[NegativeOracle, ...]
    linguistic_oracles: tuple[LinguisticOracle, ...]
    historical_references: tuple[HistoricalReferenceFixture, ...]


def _validation_failed() -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED)


def _read_models(root: Path) -> tuple[_ManifestData, _MetadataData]:
    try:
        manifest = _ManifestData.model_validate_json((root / "manifest.json").read_text())
        metadata = _MetadataData.model_validate_json(
            (root / "fixture-metadata.json").read_text()
        )
    except (OSError, ValidationError, ValueError) as error:
        raise _validation_failed() from error
    if metadata.network_dependencies or metadata.linguistic_review != "pending_human":
        raise _validation_failed()
    for name, expected in metadata.payloads.items():
        try:
            payload = (root / name).read_bytes()
        except OSError as error:
            raise _validation_failed() from error
        actual = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        if actual != expected:
            raise _validation_failed()
    return manifest, metadata


def verify_content_fixture_manifest(root: Path) -> ContentFixtureManifestVerification:
    manifest, metadata = _read_models(root)
    if manifest.kind != "positive" or manifest.expected_status != "accepted":
        raise _validation_failed()
    return ContentFixtureManifestVerification(
        fixture_id=manifest.id,
        payload_names=tuple(sorted(metadata.payloads)),
        network_dependencies=metadata.network_dependencies,
        linguistic_review=metadata.linguistic_review,
    )


def _apply_mutation(payload: dict[str, object], mutation: _MutationData) -> None:
    revisions = payload["revisions"]
    if not isinstance(revisions, list) or not revisions:
        raise _validation_failed()
    first = revisions[0]
    if not isinstance(first, dict):
        raise _validation_failed()
    if mutation.kind == "invalid-checksum":
        first["payload_checksum"] = "0" * 64
    elif mutation.kind == "invalid-provenance":
        first["provenance_id"] = "019fe005-0000-7000-8003-000000009999"
    elif mutation.kind == "invalid-rights":
        first["rights_ref"] = "unknown-license"
    else:
        manifest = payload["publication_manifest"]
        if not isinstance(manifest, dict):
            raise _validation_failed()
        manifest["checksum"] = "0" * 64


def _validate_payload(payload: _ContentPayload) -> ContentFixture:
    actor_ids = {actor.actor_id for actor in payload.actors}
    if len(actor_ids) != len(payload.actors):
        raise _validation_failed()
    provenance_ids = {item.provenance_id for item in payload.provenance}
    if not payload.provenance or any(
        not item.source_ref.startswith("FX-CONTENT") for item in payload.provenance
    ):
        raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
    for revision in payload.revisions:
        if revision.author_id not in actor_ids or (
            revision.reviewer_id is not None and revision.reviewer_id not in actor_ids
        ):
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
        if revision.provenance_id not in provenance_ids:
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
        if not revision.rights_ref.startswith(
            ("rights:fixture:", "rights:human:", "rights:import:", "rights:tool:")
        ):
            raise DomainError(ErrorCode.LICENSE_MISSING)
        if canonical_json_fingerprint(revision.payload) != revision.payload_checksum:
            raise _validation_failed()
        if revision.reviewer_id is not None and revision.reviewer_id == revision.author_id:
            raise DomainError(ErrorCode.SELF_APPROVAL_FORBIDDEN)
    publication = payload.publication_manifest
    if publication.provenance_id not in provenance_ids:
        raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
    material: dict[str, JsonValue] = {
        "content_revision_id": str(publication.content_revision_id),
        "provenance_id": str(publication.provenance_id),
        "references": [
            {
                "reference_kind": reference.reference_kind,
                "revision_id": str(reference.revision_id),
                "status": reference.status,
            }
            for reference in publication.references
        ],
    }
    if canonical_json_fingerprint(material) != publication.checksum:
        raise _validation_failed()
    if publication.content_revision_id not in {
        revision.content_revision_id
        for revision in payload.revisions
        if revision.status == "published"
    }:
        raise _validation_failed()
    revision_ids = {revision.content_revision_id for revision in payload.revisions}
    revision_by_id = {
        revision.content_revision_id: revision for revision in payload.revisions
    }
    decided_revision_ids: set[UUID] = set()
    for decision in payload.review_decisions:
        decision_revision = revision_by_id.get(decision.content_revision_id)
        if (
            decision_revision is None
            or decision.content_revision_id in decided_revision_ids
            or decision.author_id not in actor_ids
            or decision.reviewer_id not in actor_ids
            or decision.author_id == decision.reviewer_id
            or decision_revision.author_id != decision.author_id
            or decision_revision.status != decision.decision
        ):
            raise _validation_failed()
        decided_revision_ids.add(decision.content_revision_id)
    if any(
        reference.content_revision_id not in revision_ids
        or len(reference.context_checksum) != 64
        for reference in payload.historical_references
    ):
        raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
    return ContentFixture(
        synthetic=payload.synthetic,
        linguistic_review=payload.linguistic_review,
        actors=payload.actors,
        provenance=payload.provenance,
        revisions=payload.revisions,
        validation_oracles=payload.validation_oracles,
        review_decisions=payload.review_decisions,
        negative_oracles=payload.negative_oracles,
        linguistic_oracles=payload.linguistic_oracles,
        historical_references=payload.historical_references,
    )


def load_content_fixture(root: Path) -> ContentFixture:
    manifest, metadata = _read_models(root)
    try:
        if manifest.kind == "positive":
            raw = json.loads((root / "content.json").read_text())
        else:
            raw = json.loads((root.parent / "content.json").read_text())
            mutation = _MutationData.model_validate_json((root / "mutation.json").read_text())
            _apply_mutation(raw, mutation)
        payload = _ContentPayload.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise _validation_failed() from error
    if metadata.synthetic is not True or payload.fixture_id != "FX-CONTENT":
        raise _validation_failed()
    return _validate_payload(payload)
