"""API 에러 응답.

성공 응답이 {data, meta}인 것처럼 실패 응답은 {error: {code, message}} 하나로 통일한다.
FastAPI 기본 핸들러는 {"detail": ...}를 내보내므로 그대로 두면 봉투가 깨진다.
그래서 HTTPException을 쓰지 않고 ApiError를 던지며, 프레임워크가 직접 발생시키는
검증 오류도 아래 핸들러에서 같은 봉투로 바꾼다.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """명세 §에러 코드의 한 줄에 대응하는 예외."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.fields = fields

    def body(self) -> dict[str, object]:
        error: dict[str, object] = {"code": self.code, "message": self.message}
        # fields는 검증 실패일 때만 붙는다.
        if self.fields is not None:
            error["fields"] = self.fields
        return {"error": error}


class EventNotFound(ApiError):
    status_code = 404
    code = "EVENT_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 행사를 찾을 수 없습니다.")


class Unauthorized(ApiError):
    status_code = 401
    code = "UNAUTHORIZED"

    def __init__(self, message: str = "로그인이 필요합니다.") -> None:
        super().__init__(message)


class Forbidden(ApiError):
    status_code = 403
    code = "FORBIDDEN"

    def __init__(self, message: str = "권한이 없습니다.") -> None:
        super().__init__(message)


class VersionConflict(ApiError):
    """expectedVersion이 현재 값과 다를 때. 재시도 전에 리소스를 다시 조회해야 한다."""

    status_code = 409
    code = "VERSION_CONFLICT"

    def __init__(self) -> None:
        super().__init__("버전이 바뀌었습니다. 다시 조회한 뒤 시도해 주세요.")


class IdempotencyConflict(ApiError):
    """같은 Idempotency-Key에 다른 요청 본문이 왔을 때."""

    status_code = 409
    code = "IDEMPOTENCY_CONFLICT"

    def __init__(self) -> None:
        super().__init__("같은 Idempotency-Key로 다른 요청이 이미 처리되었습니다.")


class ValidationFailed(ApiError):
    status_code = 422
    code = "VALIDATION_FAILED"

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("입력을 확인해 주세요.", fields=fields)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.body())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # loc은 ("query", "size") 형태다. 마지막 요소가 FE가 고쳐야 할 이름이다.
        fields = {
            str(error["loc"][-1]): error["msg"]
            for error in exc.errors()
            if error.get("loc")
        }
        failed = ValidationFailed(fields)
        return JSONResponse(status_code=failed.status_code, content=failed.body())
