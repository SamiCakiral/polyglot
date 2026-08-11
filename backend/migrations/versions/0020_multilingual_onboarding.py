"""Add the account language repertoire and adaptive onboarding state.

Revision ID: 0020_multilingual_onboarding
Revises: 0019_assessment_audio
"""

import os

from alembic import op

revision = "0020_multilingual_onboarding"
down_revision = "0019_assessment_audio"
branch_labels = None
depends_on = None


DDL = r"""
CREATE TABLE identity.account_languages (
    account_language_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    variety_id uuid NOT NULL REFERENCES catalogue.language_varieties(variety_id) ON DELETE RESTRICT,
    relationship varchar(24) NOT NULL,
    self_assessed_band varchar(24) NOT NULL,
    use_for_explanations boolean NOT NULL,
    use_for_contrasts boolean NOT NULL,
    version integer NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    archived_at timestamptz,
    CONSTRAINT ck_account_language_uuid7 CHECK (
        identity.is_uuid7(account_language_id)
        AND identity.is_uuid7(account_id)
        AND identity.is_uuid7(variety_id)
    ),
    CONSTRAINT ck_account_language_relationship CHECK (
        relationship IN ('native', 'fluent', 'studied', 'reading_only')
    ),
    CONSTRAINT ck_account_language_band CHECK (
        self_assessed_band IN ('new', 'familiar', 'functional', 'independent', 'advanced')
    ),
    CONSTRAINT ck_account_language_version CHECK (version >= 1),
    CONSTRAINT ck_account_language_dates CHECK (
        updated_at >= created_at AND (archived_at IS NULL OR archived_at >= updated_at)
    )
);
CREATE UNIQUE INDEX uq_account_language_active
    ON identity.account_languages(account_id, variety_id)
    WHERE archived_at IS NULL;
CREATE INDEX ix_account_languages_owner
    ON identity.account_languages(account_id, relationship, updated_at DESC);

CREATE TABLE language_profiles.onboarding_states (
    profile_id uuid PRIMARY KEY REFERENCES language_profiles.learner_language_profiles(profile_id)
        ON DELETE RESTRICT,
    account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    entry_path varchar(24) NOT NULL,
    detected_band varchar(24),
    placement_confidence numeric(4,3),
    skill_profile jsonb NOT NULL,
    placement_choice varchar(24),
    calibration_sessions_remaining integer NOT NULL,
    version integer NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ck_onboarding_state_uuid7 CHECK (
        identity.is_uuid7(profile_id) AND identity.is_uuid7(account_id)
    ),
    CONSTRAINT ck_onboarding_entry_path CHECK (
        entry_path IN ('complete_beginner', 'already_started', 'advanced')
    ),
    CONSTRAINT ck_onboarding_detected_band CHECK (
        detected_band IS NULL OR detected_band IN (
            'foundations', 'emerging', 'functional', 'independent', 'advanced'
        )
    ),
    CONSTRAINT ck_onboarding_confidence CHECK (
        placement_confidence IS NULL OR placement_confidence BETWEEN 0 AND 1
    ),
    CONSTRAINT ck_onboarding_choice CHECK (
        placement_choice IS NULL OR placement_choice IN (
            'accept', 'start_easier', 'challenge', 'start_now'
        )
    ),
    CONSTRAINT ck_onboarding_calibration CHECK (
        calibration_sessions_remaining BETWEEN 0 AND 3
    ),
    CONSTRAINT ck_onboarding_version CHECK (version >= 1),
    CONSTRAINT ck_onboarding_dates CHECK (updated_at >= created_at),
    CONSTRAINT uq_onboarding_owner_profile UNIQUE(account_id, profile_id)
);

ALTER TABLE language_profiles.diagnostic_runs
    ADD COLUMN detected_band varchar(24),
    ADD COLUMN skill_profile jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD CONSTRAINT ck_diagnostic_detected_band CHECK (
        detected_band IS NULL OR detected_band IN (
            'foundations', 'emerging', 'functional', 'independent', 'advanced'
        )
    );

ALTER TABLE identity.account_languages ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_profiles.onboarding_states ENABLE ROW LEVEL SECURITY;

CREATE POLICY account_languages_owner ON identity.account_languages
    USING (account_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
    WITH CHECK (account_id = NULLIF(current_setting('app.user_id', true), '')::uuid);
CREATE POLICY onboarding_states_owner ON language_profiles.onboarding_states
    USING (account_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
    WITH CHECK (account_id = NULLIF(current_setting('app.user_id', true), '')::uuid);

ALTER TABLE identity.account_languages OWNER TO polyglot_migration;
ALTER TABLE language_profiles.onboarding_states OWNER TO polyglot_migration;
GRANT SELECT, INSERT, UPDATE ON identity.account_languages TO polyglot_runtime;
GRANT SELECT, INSERT, UPDATE ON language_profiles.onboarding_states TO polyglot_runtime;
"""


def upgrade() -> None:
    for statement in DDL.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    if os.getenv("POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE") != "true":
        raise RuntimeError("disposable-environment-only: 0020 contains personal learning state")
    op.execute(
        "ALTER TABLE language_profiles.diagnostic_runs "
        "DROP CONSTRAINT ck_diagnostic_detected_band, "
        "DROP COLUMN skill_profile, DROP COLUMN detected_band"
    )
    op.execute("DROP TABLE language_profiles.onboarding_states")
    op.execute("DROP TABLE identity.account_languages")
