"""Scope assessment definitions to their target language.

Revision ID: 0023_assessment_languages
Revises: 0022_teacher
"""

from alembic import op

revision = "0023_assessment_languages"
down_revision = "0022_teacher"
branch_labels = None
depends_on = None

ITALIAN_VARIETY_ID = "019b0000-0000-7000-8000-000000000002"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE assessments.assessment_definitions "
        "ADD COLUMN target_variety_id uuid"
    )
    op.execute(
        "UPDATE assessments.assessment_definitions SET target_variety_id="
        f"'{ITALIAN_VARIETY_ID}'::uuid WHERE definition_code LIKE 'it.%'"
    )
    op.execute(
        "ALTER TABLE assessments.assessment_definitions "
        "ALTER COLUMN target_variety_id SET NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_assessment_definitions_target_modality "
        "ON assessments.assessment_definitions(target_variety_id,modality,status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX assessments.ix_assessment_definitions_target_modality")
    op.execute(
        "ALTER TABLE assessments.assessment_definitions DROP COLUMN target_variety_id"
    )
