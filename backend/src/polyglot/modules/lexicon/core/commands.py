from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.lexicon.core.persistence import (
    CommandReceipt,
    EncounterRecord,
    LexiconRepository,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import IdGenerator, Uuid7Generator


@dataclass(frozen=True, slots=True)
class MentionCandidateInput:
    candidate_id: UUID
    sense_id: UUID
    sense_scope: str
    confidence: float
    source: str


@dataclass(frozen=True, slots=True)
class RecordLexicalEncounter:
    encounter_id: UUID
    profile_id: UUID
    exact_surface: str
    source_type: str
    source_ref: str
    source_revision_ref: str
    modality: str
    lexical_role: str
    operation: str
    help_state: str
    result_state: str
    correction_ref: str
    correction_confidence: float
    context_private: str | None
    context_fingerprint: str
    context_retention: str
    occurred_at: datetime
    mention_id: UUID
    form_analysis_id: UUID | None
    analysis_revision_ref: str
    candidates: tuple[MentionCandidateInput, ...]
    idempotency_key: str
    request_fingerprint: str

    def __post_init__(self) -> None:
        if not self.idempotency_key or len(self.request_fingerprint) != 64:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid idempotency data")
        if not self.source_revision_ref:
            raise DomainError(ErrorCode.SOURCE_REVISION_MISSING)
        if self.occurred_at.tzinfo is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="occurred_at must be aware")
        if len({item.candidate_id for item in self.candidates}) != len(self.candidates):
            raise DomainError(ErrorCode.DUPLICATE_CANDIDATE)


@dataclass(frozen=True, slots=True)
class CaptureLexicalGapCommand:
    encounter_id: UUID
    mention_id: UUID
    profile_id: UUID
    attempt_id: UUID
    intended_support_text: str
    minimal_context: str | None
    support_language_tag: str
    occurred_at: datetime
    idempotency_key: str
    request_fingerprint: str

    def __post_init__(self) -> None:
        if not self.intended_support_text.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="gap intention is required")
        if not self.support_language_tag or len(self.request_fingerprint) != 64:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid gap metadata")


@dataclass(frozen=True, slots=True)
class CreateImportedPrivateLexicalEntry:
    profile_id: UUID
    variety_id: UUID
    unit_type: str
    normalized_form: str
    semantic_key: str | None
    provenance_ref: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.normalized_form.strip() or not self.provenance_ref.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED)


class LexiconCommandService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ids: IdGenerator | None = None,
    ) -> None:
        self._session = session
        self._repository = LexiconRepository(session)
        self._ids = ids or Uuid7Generator()

    async def create_imported_private_entry(
        self,
        command: CreateImportedPrivateLexicalEntry,
    ) -> tuple[UUID, UUID]:
        unit_id = self._ids.new()
        sense_id = self._ids.new()
        await self._session.execute(
            text(
                "INSERT INTO lexicon.private_lexical_units "
                "(lexical_unit_id,profile_id,variety_id,unit_type,lemma,normalization_key,"
                "components,provenance_ref,version,created_at) VALUES "
                "(:unit,:profile,:variety,:type,:lemma,:normalization,'{}',:provenance,1,:at)"
            ),
            {
                "unit": unit_id,
                "profile": command.profile_id,
                "variety": command.variety_id,
                "type": command.unit_type,
                "lemma": command.normalized_form,
                "normalization": command.normalized_form,
                "provenance": command.provenance_ref,
                "at": command.created_at,
            },
        )
        await self._session.execute(
            text(
                "INSERT INTO lexicon.private_lexical_senses "
                "(sense_id,profile_id,lexical_unit_id,sense_code,definition,provenance_ref,"
                "created_at) VALUES "
                "(:sense,:profile,:unit,:code,:definition,:provenance,:at)"
            ),
            {
                "sense": sense_id,
                "profile": command.profile_id,
                "unit": unit_id,
                "code": command.semantic_key or f"import-{sense_id}",
                "definition": command.semantic_key or command.normalized_form,
                "provenance": command.provenance_ref,
                "at": command.created_at,
            },
        )
        return unit_id, sense_id

    async def record_encounter(self, command: RecordLexicalEncounter) -> UUID:
        receipt = await self._repository.get_command_receipt(
            profile_id=command.profile_id,
            command_name="RecordLexicalEncounter",
            idempotency_key=command.idempotency_key,
        )
        if receipt is not None:
            if receipt.request_fingerprint != command.request_fingerprint:
                raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return receipt.resource_id

        await self._repository.record_encounter(
            EncounterRecord(
                encounter_id=command.encounter_id,
                profile_id=command.profile_id,
                exact_surface=command.exact_surface,
                source_type=command.source_type,
                source_ref=command.source_ref,
                source_revision_ref=command.source_revision_ref,
                modality=command.modality,
                lexical_role=command.lexical_role,
                operation=command.operation,
                help_state=command.help_state,
                result_state=command.result_state,
                correction_ref=command.correction_ref,
                correction_confidence=command.correction_confidence,
                context_private=command.context_private,
                context_fingerprint=command.context_fingerprint,
                context_retention=command.context_retention,
                context_deleted_at=None,
                occurred_at=command.occurred_at,
                idempotency_key=command.idempotency_key,
                request_fingerprint=command.request_fingerprint,
            )
        )
        await self._session.execute(
            text(
                "INSERT INTO lexicon.lexical_mentions "
                "(mention_id,profile_id,encounter_id,exact_surface,form_analysis_id,"
                "analysis_revision_ref,ordinal,created_at) VALUES "
                "(:mention,:profile,:encounter,:surface,:form,:revision,1,:created)"
            ),
            {
                "mention": command.mention_id,
                "profile": command.profile_id,
                "encounter": command.encounter_id,
                "surface": command.exact_surface,
                "form": command.form_analysis_id,
                "revision": command.analysis_revision_ref,
                "created": command.occurred_at,
            },
        )
        for candidate in command.candidates:
            await self._session.execute(
                text(
                    "INSERT INTO lexicon.mention_candidates "
                    "(candidate_id,profile_id,mention_id,sense_id,sense_scope,confidence,source,"
                    "created_at) VALUES "
                    "(:candidate,:profile,:mention,:sense,:scope,:confidence,:source,:created)"
                ),
                {
                    "candidate": candidate.candidate_id,
                    "profile": command.profile_id,
                    "mention": command.mention_id,
                    "sense": candidate.sense_id,
                    "scope": candidate.sense_scope,
                    "confidence": candidate.confidence,
                    "source": candidate.source,
                    "created": command.occurred_at,
                },
            )
        await self._repository.save_command_receipt(
            CommandReceipt(
                receipt_id=self._ids.new(),
                profile_id=command.profile_id,
                command_name="RecordLexicalEncounter",
                idempotency_key=command.idempotency_key,
                request_fingerprint=command.request_fingerprint,
                resource_id=command.encounter_id,
                result_payload={"encounter_id": str(command.encounter_id)},
                created_at=command.occurred_at,
            )
        )
        return command.encounter_id

    async def capture_gap(self, command: CaptureLexicalGapCommand) -> UUID:
        private_context = command.minimal_context
        context_bytes = (private_context or "").encode()
        return await self.record_encounter(
            RecordLexicalEncounter(
                encounter_id=command.encounter_id,
                profile_id=command.profile_id,
                exact_surface=command.intended_support_text,
                source_type="attempt",
                source_ref=str(command.attempt_id),
                source_revision_ref=f"gap-v1:{command.support_language_tag}",
                modality="writing",
                lexical_role="production",
                operation="queried",
                help_state="self_reported",
                result_state="not_evaluable",
                correction_ref="none",
                correction_confidence=0.0,
                context_private=private_context,
                context_fingerprint=sha256(context_bytes).hexdigest(),
                context_retention="private_until_deleted",
                occurred_at=command.occurred_at,
                mention_id=command.mention_id,
                form_analysis_id=None,
                analysis_revision_ref="gap-v1",
                candidates=(),
                idempotency_key=command.idempotency_key,
                request_fingerprint=command.request_fingerprint,
            )
        )

    async def delete_private_context(
        self,
        *,
        profile_id: UUID,
        encounter_id: UUID,
        deleted_at: datetime,
    ) -> None:
        deleted = await self._repository.delete_private_context(
            profile_id=profile_id,
            encounter_id=encounter_id,
            deleted_at=deleted_at,
        )
        if not deleted:
            raise DomainError(ErrorCode.NOT_FOUND)
