# W15 phase A report

## Status

PARTIAL - phase A domain and offline ports completed. Persistence, migrations,
HTTP routes, OpenAPI, shared composition, signed URLs, external scanning and
real provider integration remain deliberately outside this phase.

## Delivered

- Immutable `MediaAsset` state machine: `reserved -> uploading -> uploaded ->
  verifying -> quarantined|processing -> ready -> deleting -> deleted`.
- Versioned media revisions, transcript segments, private opaque object keys,
  variants, rights expiration, quarantine reasons and orphan-aware deletion.
- Limits by kind, detected-MIME validation, checksum validation and hostile
  archive quarantine.
- Private-only `ObjectStoragePort`, `TtsPort` and `SttPort`, with deterministic
  fakes that make no network calls.
- TTS cache keyed by canonical request fingerprint; a missing or removed Alice
  voice returns its explicit availability and never selects another voice.
- `MacOSTtsPort` keeps `say` and `ffmpeg` behind `TtsPort`; its injected command
  runner is simulated by tests outside macOS.
- `FX-MEDIA` local fixtures cover fixed audio/transcript, retired voice, absent
  audio, deceptive MIME, hostile archive, expired rights and false checksum.
- Shadowing remains usable from transcript when audio is absent, marked
  non-evaluable rather than successful.

## TDD evidence

- RED commit `3f35f0a`: tests failed at collection because
  `polyglot.modules.media` did not exist.
- GREEN: `POLYGLOT_NETWORK_DISABLED=1 /tmp/polyglot-w15-venv/bin/pytest
  tests/unit/media tests/property/media tests/contract/media -q` -> `15 passed`.
- `ruff check src/polyglot/modules/media tests/unit/media tests/property/media
  tests/contract/media` -> `All checks passed!`.
- `mypy --cache-dir=/tmp/polyglot-w15-mypy-cache-20260810b
  src/polyglot/modules/media` -> `Success: no issues found in 4 source files`.

## Limits and follow-up gates

- No `0015_media` migration was created; W15 persistence, PostgreSQL invariants,
  object lifecycle reconciliation and signed private URLs remain future work.
- No media HTTP route or OpenAPI mutation was made.
- No real antivirus/archive scanner, bucket implementation, `say` execution or
  FFmpeg execution was performed. Their production adapters must preserve the
  explicit quarantine and no-fallback outcomes proved here.
- The isolated test environment was necessary because the shared project
  environment intermittently stalled while importing pytest cache files. The
  final targeted suite, lint and type checks all completed offline in the
  isolated environment.
