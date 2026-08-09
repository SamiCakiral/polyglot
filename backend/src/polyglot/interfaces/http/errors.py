from dataclasses import replace

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from polyglot.platform.errors import DomainError, ErrorCode

_HTTP_ERROR_CODES = {
    400: ErrorCode.VALIDATION_FAILED,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.VALIDATION_FAILED,
    409: ErrorCode.VERSION_CONFLICT,
    413: ErrorCode.SIZE_LIMIT_EXCEEDED,
    422: ErrorCode.VALIDATION_FAILED,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.DEPENDENCY_UNAVAILABLE,
}


def problem_response(
    request: Request,
    error: DomainError,
    *,
    status_override: int | None = None,
) -> JSONResponse:
    problem = error.to_problem(
        instance=request.url.path,
        request_id=request.state.request_id,
        correlation_id=request.state.correlation_id,
    )
    if status_override is not None:
        problem = replace(problem, status=status_override)
    return JSONResponse(
        status_code=problem.status,
        content=problem.as_dict(),
        media_type="application/problem+json",
        headers={
            "X-Correlation-ID": request.state.correlation_id,
            "X-Request-ID": request.state.request_id,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, error: DomainError) -> JSONResponse:
        return problem_response(request, error)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        field_errors = [
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "code": item["type"],
            }
            for item in error.errors()
        ]
        return problem_response(
            request,
            DomainError(ErrorCode.VALIDATION_FAILED, field_errors=field_errors),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        code = _HTTP_ERROR_CODES.get(
            error.status_code,
            ErrorCode.INTERNAL_ERROR if error.status_code >= 500 else ErrorCode.VALIDATION_FAILED,
        )
        return problem_response(
            request,
            DomainError(code),
            status_override=error.status_code,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _: Exception) -> JSONResponse:
        return problem_response(request, DomainError(ErrorCode.INTERNAL_ERROR))
