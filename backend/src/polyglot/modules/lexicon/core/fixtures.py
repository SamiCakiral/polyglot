import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterator
from typing import Any, cast
from uuid import UUID

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class LexiconFixture:
    has_homonyms: bool
    has_polysemy: bool
    has_syncretism: bool
    has_multiword_expression: bool
    has_private_unit: bool
    has_late_resolution: bool
    network_dependencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WordBankFixture:
    empty_profile_count: int
    small_profile_count: int
    synthetic_count: int
    seed: int
    cross_user_oracle: bool
    private_context_deleted: bool
    reference_revision: str
    network_dependencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticWordBankEntry:
    sense_id: UUID
    ordinal: int
    label: str


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{path.name} must be object")
    return cast(dict[str, Any], value)


def _validate(root: Path, payload_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _object(root / "manifest.json")
    schema_path = root.parents[2] / "contracts" / "fixtures" / "manifest.schema.json"
    if not schema_path.exists():
        schema_path = (
            Path(__file__).resolve().parents[6]
            / "contracts/fixtures/manifest.schema.json"
        )
    Draft202012Validator(_object(schema_path)).validate(manifest)
    if manifest != {"id": root.name, "kind": "positive", "expected_status": "accepted"}:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="fixture manifest is not canonical")
    metadata = _object(root / "fixture-metadata.json")
    payload_path = root / payload_name
    expected = metadata["payloads"][payload_name]
    actual = "sha256:" + hashlib.sha256(payload_path.read_bytes()).hexdigest()
    if expected != actual or metadata.get("network_dependencies") != []:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="fixture integrity mismatch")
    return _object(payload_path), metadata


def load_lexicon_fixture(root: Path) -> LexiconFixture:
    payload, metadata = _validate(root, "lexicon.json")
    cases = {item["id"]: item for item in payload["cases"]}
    piano = cases["piano-homonym"]
    return LexiconFixture(
        has_homonyms=len(piano["unit_ids"]) == 2,
        has_polysemy=len(piano["sense_ids"]) == 3,
        has_syncretism=len(cases["sono-syncretism"]["analyses"]) == 2,
        has_multiword_expression=len(cases["avere-bisogno-di"]["components"]) == 3,
        has_private_unit=cases["private-family-word"]["visibility"] == "private",
        has_late_resolution=cases["late-resolution"]["raw_fact_mutated"] is False,
        network_dependencies=tuple(metadata["network_dependencies"]),
    )


def load_word_bank_fixture(root: Path) -> WordBankFixture:
    payload, metadata = _validate(root, "word-bank.json")
    return WordBankFixture(
        empty_profile_count=int(payload["profiles"]["empty"]["sense_count"]),
        small_profile_count=int(payload["profiles"]["small"]["sense_count"]),
        synthetic_count=int(payload["synthetic_generator"]["sense_count"]),
        seed=int(payload["seed"]),
        cross_user_oracle=payload["profiles"]["cross_user"]["can_read_owner"] is False,
        private_context_deleted=payload["private_context"]["deleted"] is True,
        reference_revision=str(payload["synthetic_generator"]["reference_revision"]),
        network_dependencies=tuple(metadata["network_dependencies"]),
    )


def iter_word_bank_entries(fixture: WordBankFixture) -> Iterator[SyntheticWordBankEntry]:
    for ordinal in range(1, fixture.synthetic_count + 1):
        yield SyntheticWordBankEntry(
            UUID(f"019feb30-0000-7000-8000-{500_000 + ordinal:012x}"),
            ordinal,
            f"lemma-{ordinal:06d}",
        )


async def materialize_word_bank_fixture(
    session: AsyncSession, *, fixture: WordBankFixture, profile_id: UUID
) -> tuple[int, int]:
    reference_set_id = UUID("019feb30-0000-7000-8000-0000000927c0")
    await session.execute(
        text(
            "INSERT INTO lexicon.lexical_reference_sets "
            "(reference_set_id,code,revision,label,created_at) VALUES "
            "(:id,'fx-wb-100k',:revision,'Synthetic 100k',"
            "'2026-08-10T12:00:00+00:00')"
        ),
        {"id": reference_set_id, "revision": fixture.reference_revision},
    )
    await session.execute(
        text(
            "INSERT INTO lexicon.lexical_reference_entries "
            "(reference_set_id,sense_id,ordinal,label,definition) "
            "SELECT :reference,("
            "'019feb30-0000-7000-8000-' || lpad(to_hex(500000 + value),12,'0'))::uuid,"
            "value,'lemma-' || lpad(value::text,6,'0'),'synthetic definition ' || value "
            "FROM generate_series(1,:count) AS value"
        ),
        {"reference": reference_set_id, "count": fixture.synthetic_count},
    )
    await session.execute(
        text(
            "INSERT INTO lexicon.personal_lexical_relations "
            "(relation_id,profile_id,source_sense_id,target_sense_id,relation_type,direction,"
            "provenance_ref,confidence,created_at,version) SELECT "
            "('019feb30-0000-7000-8000-' || "
            "lpad(to_hex(700000 + ((source - 1) * 4) + stride),12,'0'))::uuid,:profile,"
            "('019feb30-0000-7000-8000-' || lpad(to_hex(500000 + source),12,'0'))::uuid,"
            "('019feb30-0000-7000-8000-' || "
            "lpad(to_hex(500000 + source + stride),12,'0'))::uuid,"
            "'association','directed','fx-wb-100k',1,'2026-08-10T12:00:00+00:00',1 "
            "FROM generate_series(1,:count) AS source CROSS JOIN generate_series(1,4) AS stride "
            "WHERE source + stride <= :count"
        ),
        {"profile": profile_id, "count": fixture.synthetic_count},
    )
    relation_count = fixture.synthetic_count * 4 - 10
    return fixture.synthetic_count, relation_count
