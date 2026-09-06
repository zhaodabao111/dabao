from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..schemas import ErrorBody, ErrorResponse, new_request_id


@dataclass
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    stage: str


def _error_response(error: ApiError) -> JSONResponse:
    payload = ErrorResponse(
        request_id=new_request_id(),
        error=ErrorBody(
            code=error.code,
            message=error.message,
            stage=error.stage,
        ),
    )
    return JSONResponse(status_code=error.status_code, content=payload.model_dump())


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        return _error_response(error)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        stage = request.url.path.strip("/").split("/", maxsplit=1)[0] or "request"
        return _error_response(
            ApiError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="请求字段缺失或类型错误，请检查后重试。",
                stage=stage,
            )
        )
