"""Allow one daily and one free sprint to coexist per profile.

Revision ID: 0024_parallel_practice
Revises: 0023_assessment_languages
"""

from alembic import op

revision = "0024_parallel_practice"
down_revision = "0023_assessment_languages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX planning.uq_planning_active_run")
    op.execute(
        "CREATE UNIQUE INDEX uq_planning_active_run "
        "ON planning.sprint_runs(profile_id,plan_kind) "
        "WHERE status IN ('in_progress','interrupted')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX planning.uq_planning_active_run")
    op.execute(
        "CREATE UNIQUE INDEX uq_planning_active_run "
        "ON planning.sprint_runs(profile_id) "
        "WHERE status IN ('in_progress','interrupted')"
    )
