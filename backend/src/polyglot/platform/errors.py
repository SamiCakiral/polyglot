from dataclasses import asdict, dataclass
from enum import StrEnum

from polyglot.platform.json_types import JsonValue


class ErrorCode(StrEnum):
    ACCOUNT_LOCKED = "account_locked"
    ACTIVE_EXPORT_OR_JOB = "active_export_or_job"
    ACTIVE_RUN_EXISTS = "active_run_exists"
    ANSWER_LEAK_DETECTED = "answer_leak_detected"
    ANSWER_SHAPE_INVALID = "answer_shape_invalid"
    ASSESSMENT_EXPIRED = "assessment_expired"
    ASSESSMENT_UNAVAILABLE = "assessment_unavailable"
    ATTEMPT_ALREADY_OPEN = "attempt_already_open"
    ATTEMPT_NOT_SUBMITTED = "attempt_not_submitted"
    BLOCK_REQUIRED = "block_required"
    BLUEPRINT_MISMATCH = "blueprint_mismatch"
    BUDGET_EXCEEDED = "budget_exceeded"
    BUDGET_INFEASIBLE = "budget_infeasible"
    CANONICAL_SENSE_IMMUTABLE = "canonical_sense_immutable"
    CASE_ALREADY_OPEN = "case_already_open"
    COMPLETION_CRITERIA_MISSING = "completion_criteria_missing"
    CONFIDENCE_INCONSISTENT = "confidence_inconsistent"
    CONFLICT_ACTION_INVALID = "conflict_action_invalid"
    CONSENT_PURPOSE_UNKNOWN = "consent_purpose_unknown"
    CONTENT_UNAVAILABLE = "content_unavailable"
    CORRECTION_PATH_MISSING = "correction_path_missing"
    CURSOR_INVALID = "cursor_invalid"
    DAY_REVISION_INVALID = "day_revision_invalid"
    DELAYED_SOURCE_INVALID = "delayed_source_invalid"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    DIAGNOSTIC_UNAVAILABLE = "diagnostic_unavailable"
    DRAFT_NOT_FOUND = "draft_not_found"
    DRAFT_STALE = "draft_stale"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    EVIDENCE_SCOPE_FORBIDDEN = "evidence_scope_forbidden"
    FIELD_GROUP_FORBIDDEN = "field_group_forbidden"
    FILTER_INVALID = "filter_invalid"
    FORBIDDEN = "forbidden"
    FOUNDATION_PACK_MISSING = "foundation_pack_missing"
    GATE_NOT_READY = "gate_not_ready"
    HINT_NOT_AVAILABLE = "hint_not_available"
    HISTORICAL_RIGHTS_CONFLICT = "historical_rights_conflict"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    IDENTITY_CONFLICT = "identity_conflict"
    IDENTITY_PROVIDER_MISMATCH = "identity_provider_mismatch"
    INCOMPATIBLE_PROTOCOLS = "incompatible_protocols"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    INTERNAL_ERROR = "internal_error"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_TRANSITION = "invalid_transition"
    JOB_NOT_CANCELLABLE = "job_not_cancellable"
    LANGUAGE_NOT_CERTIFIED = "language_not_certified"
    LICENSE_MISSING = "license_missing"
    LIST_MERGE_CONFLICT = "list_merge_conflict"
    LIST_NOT_SHAREABLE = "list_not_shareable"
    LOAD_BUDGET_EXCEEDED = "load_budget_exceeded"
    MANDATE_MISSING = "mandate_missing"
    MEDIA_INTEGRITY_FAILED = "media_integrity_failed"
    MEDIA_NOT_READY = "media_not_ready"
    MEDIA_QUOTA_EXCEEDED = "media_quota_exceeded"
    MEDIA_STILL_REQUIRED = "media_still_required"
    MEMBER_CONFLICT = "member_conflict"
    MERGE_AMBIGUOUS = "merge_ambiguous"
    MODE_UNSUPPORTED = "mode_unsupported"
    MODULE_EXIT_UNMEASURABLE = "module_exit_unmeasurable"
    MODULE_VALIDATION_FAILED = "module_validation_failed"
    NO_VALID_COMPOSITION = "no_valid_composition"
    NOT_FOUND = "not_found"
    NOVELTY_LIMIT_EXCEEDED = "novelty_limit_exceeded"
    OBSERVATION_TARGET_NOT_DISCRIMINANT = "observation_target_not_discriminant"
    PACK_INCOMPATIBLE = "pack_incompatible"
    PACK_NOT_PUBLISHED = "pack_not_published"
    PAUSE_NOT_ALLOWED = "pause_not_allowed"
    PREREQUISITE_CYCLE = "prerequisite_cycle"
    PREREQUISITE_MISSING = "prerequisite_missing"
    PREVIEW_STALE = "preview_stale"
    PRIMITIVE_UNKNOWN = "primitive_unknown"
    PRIVATE_CONTEXT_FORBIDDEN = "private_context_forbidden"
    PRIVATE_CONTEXT_NOT_CONSENTED = "private_context_not_consented"
    PRIVATE_CONTEXT_PRESENT = "private_context_present"
    PROFILE_ALREADY_EXISTS = "profile_already_exists"
    PROFILE_DELETED = "profile_deleted"
    PROJECTION_VERSION_UNAVAILABLE = "projection_version_unavailable"
    PROMPT_CONFLICT = "prompt_conflict"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PUBLICATION_NOT_ACTIVE = "publication_not_active"
    RATE_LIMITED = "rate_limited"
    RATING_NOT_ALLOWED = "rating_not_allowed"
    RECOMMENDATION_EXPIRED = "recommendation_expired"
    REFERENCE_NOT_FOUND = "reference_not_found"
    REFERENCE_NOT_PUBLISHABLE = "reference_not_publishable"
    RELATION_INVALID = "relation_invalid"
    REPORT_SCOPE_FORBIDDEN = "report_scope_forbidden"
    REQUIRED_BLOCK_INCOMPLETE = "required_block_incomplete"
    REQUIRED_BLOCK_NOT_CORRECTABLE = "required_block_not_correctable"
    RESOURCE_REUSED = "resource_reused"
    RESOURCE_REVISION_MISSING = "resource_revision_missing"
    RESPONSE_CONFLICT = "response_conflict"
    RESPONSE_STALE = "response_stale"
    REVIEW_CONFLICT = "review_conflict"
    RUBRIC_MISMATCH = "rubric_mismatch"
    RUBRIC_STALE = "rubric_stale"
    RUN_ALREADY_STARTED = "run_already_started"
    RUN_EXPIRED = "run_expired"
    SELF_APPROVAL_FORBIDDEN = "self_approval_forbidden"
    SCOPE_FORBIDDEN = "scope_forbidden"
    SENSE_AMBIGUOUS = "sense_ambiguous"
    SENSE_OUT_OF_SCOPE = "sense_out_of_scope"
    SIZE_LIMIT_EXCEEDED = "size_limit_exceeded"
    SNAPSHOT_IMMUTABLE = "snapshot_immutable"
    SNAPSHOT_STALE = "snapshot_stale"
    SOURCE_REVISION_MISSING = "source_revision_missing"
    SUPPORT_LANGUAGE_NOT_ALLOWED = "support_language_not_allowed"
    TARGET_NOT_PUBLISHED = "target_not_published"
    TARGET_REVISION_UNAVAILABLE = "target_revision_unavailable"
    TIMEOUT = "timeout"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    TOOL_SCHEMA_INVALID = "tool_schema_invalid"
    UNAUTHENTICATED = "unauthenticated"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    UNSUPPORTED_IMPORT_FORMAT = "unsupported_import_format"
    VALIDATION_FAILED = "validation_failed"
    VALIDATOR_PACK_INCOMPATIBLE = "validator_pack_incompatible"
    VALIDATOR_UNAVAILABLE = "validator_unavailable"
    VERSION_CONFLICT = "version_conflict"


_HTTP_STATUS_BY_CODE = dict.fromkeys(ErrorCode, 409)
_HTTP_STATUS_BY_CODE.update(
    {
        ErrorCode.ACCOUNT_LOCKED: 423,
        ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
        ErrorCode.FORBIDDEN: 403,
        ErrorCode.INTERNAL_ERROR: 500,
        ErrorCode.INVALID_CREDENTIALS: 401,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.PROVIDER_UNAVAILABLE: 503,
        ErrorCode.RATE_LIMITED: 429,
        ErrorCode.TIMEOUT: 504,
        ErrorCode.UNAUTHENTICATED: 401,
        ErrorCode.VALIDATION_FAILED: 422,
    }
)
_RETRYABLE_CODES = frozenset(
    {
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        ErrorCode.PROVIDER_UNAVAILABLE,
        ErrorCode.RATE_LIMITED,
        ErrorCode.TIMEOUT,
    }
)


@dataclass(frozen=True, slots=True)
class ProblemDetail:
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    message_key: str
    request_id: str
    correlation_id: str
    retryable: bool
    details: dict[str, JsonValue] | None = None
    field_errors: list[dict[str, JsonValue]] | None = None

    def as_dict(self) -> dict[str, JsonValue]:
        return {key: value for key, value in asdict(self).items() if value is not None}


class DomainError(Exception):
    def __init__(
        self,
        code: ErrorCode | str,
        *,
        detail: str | None = None,
        retryable: bool | None = None,
        details: dict[str, JsonValue] | None = None,
        field_errors: list[dict[str, JsonValue]] | None = None,
    ) -> None:
        self.code = ErrorCode(code)
        self.detail = detail or self.code.value.replace("_", " ").capitalize()
        self.http_status = _HTTP_STATUS_BY_CODE[self.code]
        self.retryable = self.code in _RETRYABLE_CODES if retryable is None else retryable
        self.details = details
        self.field_errors = field_errors
        super().__init__(self.detail)

    @property
    def type_uri(self) -> str:
        return f"https://polyglot.example/problems/{self.code.value.replace('_', '-')}"

    @property
    def message_key(self) -> str:
        return f"errors.{self.code.value}"

    def to_problem(
        self,
        *,
        instance: str,
        request_id: str,
        correlation_id: str,
    ) -> ProblemDetail:
        return ProblemDetail(
            type=self.type_uri,
            title=self.code.value.replace("_", " ").title(),
            status=self.http_status,
            detail=self.detail,
            instance=instance,
            code=self.code.value,
            message_key=self.message_key,
            request_id=request_id,
            correlation_id=correlation_id,
            retryable=self.retryable,
            details=self.details,
            field_errors=self.field_errors,
        )
