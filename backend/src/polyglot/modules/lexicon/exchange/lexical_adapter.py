from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.lexicon.core.commands import (
    CreateImportedPrivateLexicalEntry,
    LexiconCommandService,
)
from polyglot.modules.lexicon.core.persistence import LexiconRepository
from polyglot.modules.lexicon.exchange.ports import (
    CreateImportedLexicalEntry,
    ResolvedLexicalCandidate,
)
from polyglot.platform.ids import IdGenerator


class SqlLexicalMutationAdapter:
    """Maps W08 imports to the W06 command boundary in the caller's transaction."""

    def __init__(self, ids: IdGenerator) -> None:
        self._ids = ids

    async def create_imported_entry(
        self,
        command: CreateImportedLexicalEntry,
        *,
        session: AsyncSession,
    ) -> tuple[str, str]:
        unit_id, sense_id = await LexiconCommandService(
            session,
            ids=self._ids,
        ).create_imported_private_entry(
            CreateImportedPrivateLexicalEntry(
                profile_id=command.profile_id,
                variety_id=command.variety_id,
                unit_type=command.unit_type,
                normalized_form=command.normalized_form,
                semantic_key=command.semantic_key,
                provenance_ref=command.provenance_ref,
                created_at=command.created_at,
            )
        )
        return f"lexical_unit:{unit_id}", f"lexical_sense:{sense_id}"


class SqlLexicalReferenceAdapter:
    async def list_import_candidates(
        self,
        profile_id: UUID,
        *,
        session: AsyncSession,
    ) -> tuple[ResolvedLexicalCandidate, ...]:
        records = await LexiconRepository(session).list_private_import_candidates(profile_id)
        return tuple(
            ResolvedLexicalCandidate(
                entity_ref=f"lexical_sense:{record.sense_id}",
                variety_id=record.variety_id,
                unit_type=record.unit_type,
                normalized_form=record.normalization_key,
                semantic_key=record.sense_code,
                visibility="private",
            )
            for record in records
        )
