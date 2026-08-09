from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from polyglot.platform.errors import DomainError, ErrorCode


def problem_response(request: Request, error: DomainError) -> JSONResponse:
    problem = error.to_problem(
        instance=request.url.path,
        request_id=request.state.request_id,
        correlation_id=request.state.correlation_id,
    )
    return JSONResponse(
        status_code=problem.status,
        content=problem.as_dict(),
        media_type="application/problem+json",
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
        if error.status_code == 404:
            return problem_response(request, DomainError(ErrorCode.NOT_FOUND))
        return problem_response(request, DomainError(ErrorCode.INTERNAL_ERROR))
