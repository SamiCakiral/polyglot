"""Persist private media, uploads, derivatives and TTS capabilities.

Revision ID: 0015_media
Revises: 0014_assessments
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0015_media"
down_revision = "0014_assessments"
branch_labels = None
depends_on = None


MEDIA_DDL = r"""
CREATE SCHEMA media AUTHORIZATION polyglot_migration;

CREATE FUNCTION media.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION media.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION media.guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'media fact is append-only' USING ERRCODE='55000';
END
$function$;
CREATE FUNCTION media.guard_revision_after_ready() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE asset_status text;
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'media revision is append-only' USING ERRCODE='55000';
  END IF;
  SELECT status INTO asset_status FROM media.media_assets WHERE media_id=OLD.media_id;
  IF asset_status IN ('ready','deleting','deleted') THEN
    RAISE EXCEPTION 'ready media revision is immutable' USING ERRCODE='55000';
  END IF;
  RETURN NEW;
END
$function$;

CREATE TABLE media.media_assets (
  media_id uuid PRIMARY KEY,
  owner_account_id uuid REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  editorial_owner_id uuid REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  media_type varchar(16) NOT NULL,
  status varchar(24) NOT NULL,
  privacy_class varchar(16) NOT NULL,
  current_revision_id uuid,
  expires_at timestamptz,
  deletion_requested_at timestamptz,
  quarantine_reason varchar(40),
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_media_asset_owner UNIQUE (owner_account_id,media_id),
  CONSTRAINT ck_media_asset_uuid7 CHECK (
    media.is_uuid7(media_id)
    AND (owner_account_id IS NULL OR media.is_uuid7(owner_account_id))
    AND (editorial_owner_id IS NULL OR media.is_uuid7(editorial_owner_id))
    AND (current_revision_id IS NULL OR media.is_uuid7(current_revision_id))
  ),
  CONSTRAINT ck_media_asset_shape CHECK (
    (owner_account_id IS NULL) <> (editorial_owner_id IS NULL)
    AND media_type IN ('image','audio','video','archive')
    AND status IN ('reserved','uploading','uploaded','verifying','quarantined','processing','ready','rejected','failed','deleting','deleted')
    AND privacy_class IN ('personal','sensitive','public','internal')
    AND version>=1 AND updated_at>=created_at
    AND ((status='quarantined')=(quarantine_reason IS NOT NULL))
  )
);

CREATE TABLE media.media_rights (
  rights_id uuid PRIMARY KEY,
  media_id uuid NOT NULL REFERENCES media.media_assets(media_id) ON DELETE RESTRICT,
  owner_account_id uuid,
  license_ref varchar(240) NOT NULL,
  provenance_ref varchar(240) NOT NULL,
  consent_id uuid,
  source_ref varchar(400),
  expires_at timestamptz,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_media_rights_owner UNIQUE (owner_account_id,rights_id),
  CONSTRAINT ck_media_rights_uuid7 CHECK (
    media.is_uuid7(rights_id) AND media.is_uuid7(media_id)
    AND (owner_account_id IS NULL OR media.is_uuid7(owner_account_id))
    AND (consent_id IS NULL OR media.is_uuid7(consent_id))
  ),
  CONSTRAINT ck_media_rights_shape CHECK (length(license_ref)>=1 AND length(provenance_ref)>=1)
);

CREATE TABLE media.media_revisions (
  media_revision_id uuid PRIMARY KEY,
  media_id uuid NOT NULL REFERENCES media.media_assets(media_id) ON DELETE RESTRICT,
  owner_account_id uuid,
  rights_id uuid NOT NULL REFERENCES media.media_rights(rights_id) ON DELETE RESTRICT,
  revision_no integer NOT NULL,
  storage_key varchar(240) NOT NULL UNIQUE,
  declared_mime varchar(120) NOT NULL,
  detected_mime varchar(120),
  sha256 char(64) NOT NULL,
  size_bytes bigint,
  duration_ms integer,
  variety_id uuid,
  transcript_text text,
  processing_version varchar(80),
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_media_revision_no UNIQUE (media_id,revision_no),
  CONSTRAINT uq_media_revision_owner UNIQUE (owner_account_id,media_revision_id),
  CONSTRAINT uq_media_revision_asset UNIQUE (media_id,media_revision_id),
  CONSTRAINT ck_media_revision_uuid7 CHECK (
    media.is_uuid7(media_revision_id) AND media.is_uuid7(media_id)
    AND media.is_uuid7(rights_id)
    AND (owner_account_id IS NULL OR media.is_uuid7(owner_account_id))
    AND (variety_id IS NULL OR media.is_uuid7(variety_id))
  ),
  CONSTRAINT ck_media_revision_shape CHECK (
    revision_no>=1 AND storage_key ~ '^media/[0-9a-f-]+$'
    AND sha256 ~ '^[0-9a-f]{64}$' AND (size_bytes IS NULL OR size_bytes>=0)
    AND (duration_ms IS NULL OR duration_ms>=0)
  )
);
ALTER TABLE media.media_assets ADD CONSTRAINT fk_media_current_revision
  FOREIGN KEY (media_id,current_revision_id)
  REFERENCES media.media_revisions(media_id,media_revision_id) ON DELETE RESTRICT;

CREATE TABLE media.media_uploads (
  upload_id uuid PRIMARY KEY,
  media_id uuid NOT NULL,
  media_revision_id uuid NOT NULL,
  owner_account_id uuid NOT NULL,
  reserved_by_actor_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  expected_size bigint NOT NULL,
  expected_sha256 char(64) NOT NULL,
  declared_mime varchar(120) NOT NULL,
  byte_limit bigint NOT NULL,
  status varchar(24) NOT NULL,
  reserved_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  uploaded_at timestamptz,
  completed_at timestamptz,
  detected_mime varchar(120),
  actual_sha256 char(64),
  actual_size bigint,
  scan_result varchar(40),
  version integer NOT NULL,
  idempotency_key varchar(255) NOT NULL,
  request_fingerprint char(64) NOT NULL,
  CONSTRAINT fk_media_upload_asset FOREIGN KEY (owner_account_id,media_id)
    REFERENCES media.media_assets(owner_account_id,media_id) ON DELETE RESTRICT,
  CONSTRAINT fk_media_upload_revision FOREIGN KEY (owner_account_id,media_revision_id)
    REFERENCES media.media_revisions(owner_account_id,media_revision_id) ON DELETE RESTRICT,
  CONSTRAINT uq_media_upload_idempotency UNIQUE (owner_account_id,idempotency_key),
  CONSTRAINT ck_media_upload_uuid7 CHECK (
    media.is_uuid7(upload_id) AND media.is_uuid7(media_id)
    AND media.is_uuid7(media_revision_id) AND media.is_uuid7(owner_account_id)
    AND media.is_uuid7(reserved_by_actor_id)
  ),
  CONSTRAINT ck_media_upload_shape CHECK (
    expected_size>=0 AND expected_size<=byte_limit AND byte_limit>0
    AND expected_sha256 ~ '^[0-9a-f]{64}$'
    AND status IN ('reserved','uploading','uploaded','verifying','quarantined','processing','ready','rejected','failed','deleting','deleted')
    AND expires_at>reserved_at AND version>=1 AND request_fingerprint ~ '^[0-9a-f]{64}$'
    AND (actual_sha256 IS NULL OR actual_sha256 ~ '^[0-9a-f]{64}$')
    AND (actual_size IS NULL OR actual_size>=0)
  )
);

CREATE TABLE media.media_variants (
  variant_id uuid PRIMARY KEY,
  media_revision_id uuid NOT NULL REFERENCES media.media_revisions(media_revision_id) ON DELETE RESTRICT,
  media_id uuid NOT NULL REFERENCES media.media_assets(media_id) ON DELETE RESTRICT,
  owner_account_id uuid,
  variant_type varchar(80) NOT NULL,
  storage_key varchar(240) NOT NULL UNIQUE,
  mime_type varchar(120) NOT NULL,
  sha256 char(64) NOT NULL,
  size_bytes bigint NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_media_variant_type UNIQUE (media_revision_id,variant_type),
  CONSTRAINT ck_media_variant_uuid7 CHECK (
    media.is_uuid7(variant_id) AND media.is_uuid7(media_revision_id)
    AND media.is_uuid7(media_id)
    AND (owner_account_id IS NULL OR media.is_uuid7(owner_account_id))
  ),
  CONSTRAINT ck_media_variant_shape CHECK (
    length(variant_type)>=1 AND storage_key ~ '^media/[0-9a-f-]+$'
    AND sha256 ~ '^[0-9a-f]{64}$' AND size_bytes>=0
  )
);

CREATE TABLE media.media_segments (
  segment_id uuid PRIMARY KEY,
  media_revision_id uuid NOT NULL REFERENCES media.media_revisions(media_revision_id) ON DELETE RESTRICT,
  media_id uuid NOT NULL REFERENCES media.media_assets(media_id) ON DELETE RESTRICT,
  owner_account_id uuid,
  ordinal integer NOT NULL,
  start_ms integer NOT NULL,
  end_ms integer NOT NULL,
  transcript_text text,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_media_segment_ordinal UNIQUE (media_revision_id,ordinal),
  CONSTRAINT ck_media_segment_uuid7 CHECK (
    media.is_uuid7(segment_id) AND media.is_uuid7(media_revision_id)
    AND media.is_uuid7(media_id)
    AND (owner_account_id IS NULL OR media.is_uuid7(owner_account_id))
  ),
  CONSTRAINT ck_media_segment_shape CHECK (ordinal>=1 AND start_ms>=0 AND end_ms>start_ms)
);

CREATE TABLE media.oral_assets (
  oral_asset_id uuid PRIMARY KEY,
  media_revision_id uuid NOT NULL REFERENCES media.media_revisions(media_revision_id) ON DELETE RESTRICT,
  media_id uuid NOT NULL REFERENCES media.media_assets(media_id) ON DELETE RESTRICT,
  owner_account_id uuid,
  transcript_revision_id uuid,
  speaker_or_voice_ref varchar(120) NOT NULL,
  reference_rate numeric(6,3) NOT NULL,
  register varchar(80) NOT NULL,
  segment_ids uuid[] NOT NULL,
  provenance_id uuid NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT ck_oral_asset_uuid7 CHECK (
    media.is_uuid7(oral_asset_id) AND media.is_uuid7(media_revision_id)
    AND media.is_uuid7(media_id) AND media.is_uuid7(provenance_id)
    AND (owner_account_id IS NULL OR media.is_uuid7(owner_account_id))
    AND (transcript_revision_id IS NULL OR media.is_uuid7(transcript_revision_id))
  ),
  CONSTRAINT ck_oral_asset_shape CHECK (reference_rate>0 AND cardinality(segment_ids)>=1)
);

CREATE TABLE media.tts_voice_catalog_revisions (
  catalog_revision_id uuid PRIMARY KEY,
  provider_code varchar(80) NOT NULL,
  provider_version varchar(80) NOT NULL,
  published_at timestamptz NOT NULL,
  checksum char(64) NOT NULL,
  CONSTRAINT uq_tts_catalog_revision UNIQUE (provider_code,provider_version),
  CONSTRAINT ck_tts_catalog_uuid7 CHECK (media.is_uuid7(catalog_revision_id)),
  CONSTRAINT ck_tts_catalog_shape CHECK (checksum ~ '^[0-9a-f]{64}$')
);

CREATE TABLE media.tts_voice_capabilities (
  catalog_revision_id uuid NOT NULL REFERENCES media.tts_voice_catalog_revisions(catalog_revision_id) ON DELETE RESTRICT,
  voice_id varchar(120) NOT NULL,
  language_tags varchar(40)[] NOT NULL,
  formats varchar(40)[] NOT NULL,
  limits jsonb NOT NULL,
  availability varchar(32) NOT NULL,
  PRIMARY KEY (catalog_revision_id,voice_id),
  CONSTRAINT ck_tts_voice_shape CHECK (
    cardinality(language_tags)>=1 AND cardinality(formats)>=1 AND jsonb_typeof(limits)='object'
    AND availability IN ('available','temporarily_unavailable','retired','unsupported')
  )
);

CREATE TABLE media.tts_cache_entries (
  cache_entry_id uuid PRIMARY KEY,
  owner_account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  catalog_revision_id uuid NOT NULL,
  voice_id varchar(120) NOT NULL,
  cache_key char(64) NOT NULL,
  media_id uuid NOT NULL REFERENCES media.media_assets(media_id) ON DELETE RESTRICT,
  media_revision_id uuid NOT NULL REFERENCES media.media_revisions(media_revision_id) ON DELETE RESTRICT,
  locale varchar(40) NOT NULL,
  parameters jsonb NOT NULL,
  status varchar(32) NOT NULL,
  created_at timestamptz NOT NULL,
  last_accessed_at timestamptz NOT NULL,
  CONSTRAINT fk_tts_cache_voice FOREIGN KEY (catalog_revision_id,voice_id)
    REFERENCES media.tts_voice_capabilities(catalog_revision_id,voice_id) ON DELETE RESTRICT,
  CONSTRAINT uq_tts_cache_key UNIQUE (owner_account_id,cache_key),
  CONSTRAINT ck_tts_cache_uuid7 CHECK (
    media.is_uuid7(cache_entry_id) AND media.is_uuid7(owner_account_id)
    AND media.is_uuid7(catalog_revision_id) AND media.is_uuid7(media_id)
    AND media.is_uuid7(media_revision_id)
  ),
  CONSTRAINT ck_tts_cache_shape CHECK (
    cache_key ~ '^[0-9a-f]{64}$' AND jsonb_typeof(parameters)='object'
    AND status IN ('ready','temporarily_unavailable','retired','unsupported')
    AND last_accessed_at>=created_at
  )
);

CREATE TABLE media.tts_synthesis_requests (
  request_id uuid PRIMARY KEY,
  owner_account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  idempotency_key varchar(255) NOT NULL,
  request_fingerprint char(64) NOT NULL,
  voice_id varchar(120) NOT NULL,
  availability varchar(32),
  cache_key char(64),
  media_id uuid REFERENCES media.media_assets(media_id) ON DELETE RESTRICT,
  status varchar(16) NOT NULL,
  created_at timestamptz NOT NULL,
  completed_at timestamptz,
  CONSTRAINT uq_tts_synthesis_idempotency UNIQUE (owner_account_id,idempotency_key),
  CONSTRAINT ck_tts_synthesis_uuid7 CHECK (
    media.is_uuid7(request_id) AND media.is_uuid7(owner_account_id)
    AND (media_id IS NULL OR media.is_uuid7(media_id))
  ),
  CONSTRAINT ck_tts_synthesis_shape CHECK (
    request_fingerprint ~ '^[0-9a-f]{64}$'
    AND (cache_key IS NULL OR cache_key ~ '^[0-9a-f]{64}$')
    AND status IN ('started','completed')
    AND (availability IS NULL OR availability IN
      ('available','temporarily_unavailable','retired','unsupported'))
    AND ((status='started' AND availability IS NULL AND completed_at IS NULL)
      OR (status='completed' AND availability IS NOT NULL AND completed_at IS NOT NULL))
  )
);

DO $guards$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'media_rights','media_variants','media_segments','oral_assets',
    'tts_voice_catalog_revisions','tts_voice_capabilities'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON media.%I FOR EACH ROW EXECUTE FUNCTION media.guard_append_only()',
      'guard_' || table_name,table_name
    );
  END LOOP;
END
$guards$;
CREATE TRIGGER guard_media_revisions
  BEFORE UPDATE OR DELETE ON media.media_revisions
  FOR EACH ROW EXECUTE FUNCTION media.guard_revision_after_ready();

DO $public_rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['tts_voice_catalog_revisions','tts_voice_capabilities'] LOOP
    EXECUTE format('ALTER TABLE media.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE media.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format('CREATE POLICY %I ON media.%I FOR SELECT USING (true)',table_name || '_read',table_name);
    EXECUTE format('CREATE POLICY %I ON media.%I TO polyglot_migration USING (true) WITH CHECK (true)',table_name || '_migration',table_name);
  END LOOP;
END
$public_rls$;
DO $owner_rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'media_assets','media_rights','media_revisions','media_uploads','media_variants',
    'media_segments','oral_assets','tts_cache_entries','tts_synthesis_requests'
  ] LOOP
    EXECUTE format('ALTER TABLE media.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE media.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON media.%I USING (owner_account_id=media.current_user_id()) WITH CHECK (owner_account_id=media.current_user_id())',
      table_name || '_owner',table_name
    );
    EXECUTE format('CREATE POLICY %I ON media.%I TO polyglot_migration USING (true) WITH CHECK (true)',table_name || '_migration',table_name);
  END LOOP;
END
$owner_rls$;

GRANT USAGE ON SCHEMA media TO polyglot_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA media TO polyglot_runtime;
GRANT INSERT,UPDATE ON media.media_assets,media.media_uploads,media.tts_cache_entries,
  media.tts_synthesis_requests TO polyglot_runtime;
GRANT INSERT ON media.media_rights,media.media_variants,
  media.media_segments,media.oral_assets TO polyglot_runtime;
GRANT INSERT,UPDATE ON media.media_revisions TO polyglot_runtime;
REVOKE DELETE ON ALL TABLES IN SCHEMA media FROM polyglot_runtime;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA media TO polyglot_migration;
REVOKE ALL ON ALL TABLES IN SCHEMA media FROM PUBLIC;

INSERT INTO media.tts_voice_catalog_revisions
  (catalog_revision_id,provider_code,provider_version,published_at,checksum)
VALUES
  ('019feb37-0000-7000-8000-000000000001','macos-say','local-v1','2026-08-10T00:00:00Z',
   'df747e8ef4d27f93f8ee588b2b1fc596f67d515b5ad81974eb7fd66fe14de7ed');
INSERT INTO media.tts_voice_capabilities
  (catalog_revision_id,voice_id,language_tags,formats,limits,availability)
VALUES
  ('019feb37-0000-7000-8000-000000000001','Alice',ARRAY['it-IT'],ARRAY['audio/mpeg'],
   '{"max_text_chars":5000,"speed_min":100,"speed_max":300}','available');

ALTER FUNCTION media.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION media.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION media.guard_append_only() OWNER TO polyglot_migration;
ALTER FUNCTION media.guard_revision_after_ready() OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN
  FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='media' LOOP
    EXECUTE format('ALTER TABLE media.%I OWNER TO polyglot_migration',item.tablename);
  END LOOP;
END $owners$;
"""


DROP_DDL = "DROP SCHEMA IF EXISTS media CASCADE;"


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, MEDIA_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
