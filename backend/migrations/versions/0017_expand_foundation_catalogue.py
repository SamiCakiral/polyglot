"""Allow published foundation catalogues to grow beyond the original ten items.

Revision ID: 0017_expand_foundations
Revises: 0016_generation
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0017_expand_foundations"
down_revision: str | None = "0016_generation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


VALIDATE_FOUNDATION_GATE = """
CREATE OR REPLACE FUNCTION catalogue.validate_foundation_gate() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    definition_pack_revision_id uuid;
    definition_code varchar;
    ordered_codes varchar[];
BEGIN
    SELECT revision.pack_revision_id, definition.foundation_code
      INTO definition_pack_revision_id, definition_code
    FROM catalogue.foundation_definition_revisions AS revision
    JOIN catalogue.foundation_definitions AS definition
      ON definition.foundation_id = revision.foundation_id
    WHERE revision.foundation_revision_id = NEW.foundation_revision_id;
    IF definition_pack_revision_id IS DISTINCT FROM NEW.pack_revision_id
       OR definition_code IS DISTINCT FROM NEW.gate_code THEN
        RAISE EXCEPTION 'foundation gate does not match definition' USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(block_code ORDER BY ordinal)
      INTO ordered_codes
    FROM catalogue.foundation_block_revisions
    WHERE foundation_revision_id = NEW.foundation_revision_id
      AND pack_revision_id = NEW.pack_revision_id
      AND status = 'published';
    IF ordered_codes IS DISTINCT FROM ARRAY['F1', 'F2', 'F3', 'F4', 'F5']::varchar[]
       OR (SELECT count(*) FROM catalogue.foundation_item_revisions AS item
           JOIN catalogue.foundation_block_revisions AS block
             ON block.block_revision_id = item.block_revision_id
           WHERE block.foundation_revision_id = NEW.foundation_revision_id
             AND item.pack_revision_id = NEW.pack_revision_id
             AND item.status = 'published') < 10 THEN
        RAISE EXCEPTION 'foundation definition is incomplete' USING ERRCODE = '23514';
    END IF;
    IF cardinality(NEW.blocking_target_refs) <>
       (SELECT count(DISTINCT target_ref) FROM unnest(NEW.blocking_target_refs) AS target_ref)
       OR EXISTS (
        SELECT 1
        FROM unnest(NEW.blocking_target_refs) AS requested(target_ref)
        WHERE NOT EXISTS (
            SELECT 1
            FROM catalogue.foundation_item_revisions AS item
            JOIN catalogue.foundation_block_revisions AS block
              ON block.block_revision_id = item.block_revision_id
            CROSS JOIN unnest(item.target_refs) AS declared(target_ref)
            WHERE block.foundation_revision_id = NEW.foundation_revision_id
              AND item.pack_revision_id = NEW.pack_revision_id
              AND item.checker_kind <> 'not_evaluable'
              AND declared.target_ref = requested.target_ref
        )
    ) OR EXISTS (
        SELECT 1
        FROM catalogue.foundation_item_revisions AS item
        JOIN catalogue.foundation_block_revisions AS block
          ON block.block_revision_id = item.block_revision_id
        CROSS JOIN unnest(item.target_refs) AS declared(target_ref)
        WHERE block.foundation_revision_id = NEW.foundation_revision_id
          AND item.pack_revision_id = NEW.pack_revision_id
          AND item.checker_kind <> 'not_evaluable'
          AND NOT declared.target_ref = ANY(NEW.blocking_target_refs)
    ) THEN
        RAISE EXCEPTION 'foundation gate references missing target' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
"""


def upgrade() -> None:
    op.execute(VALIDATE_FOUNDATION_GATE)
    op.execute(
        "ALTER FUNCTION catalogue.validate_foundation_gate() OWNER TO polyglot_migration"
    )


def downgrade() -> None:
    if os.getenv("POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE") != "true":
        raise RuntimeError(
            "disposable-environment-only: 0017 cannot safely restore the obsolete "
            "exact-ten-item constraint"
        )
