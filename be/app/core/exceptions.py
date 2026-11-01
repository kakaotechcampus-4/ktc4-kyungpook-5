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


class IdempotencyInProgress(ApiError):
    """같은 Idempotency-Key의 첫 요청이 아직 처리 중일 때.

    다시 실행하면 AI를 두 번 부르므로 막는다(#203 멘토 리뷰). 클라이언트는 잠시 뒤
    같은 키로 다시 보내면 완료된 응답을 그대로 받는다.
    """

    status_code = 409
    code = "IDEMPOTENCY_IN_PROGRESS"

    def __init__(self) -> None:
        super().__init__("같은 요청을 처리하고 있어요. 잠시 뒤 다시 시도해 주세요.")


class ExpenseNotFound(ApiError):
    status_code = 404
    code = "EXPENSE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 지출 내역을 찾을 수 없습니다.")


class ReceiptImportNotFound(ApiError):
    status_code = 404
    code = "RECEIPT_IMPORT_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("해당 영수 내역 초안을 찾을 수 없습니다.")


class ImportNotReady(ApiError):
    """검수 전(QUEUED/PROCESSING)이거나 이미 CONFIRMED/FAILED인 초안을 확정하려 할 때."""

    status_code = 409
    code = "IMPORT_NOT_READY"

    def __init__(self) -> None:
        super().__init__("아직 확정할 수 있는 상태가 아닙니다.")


class ValidationFailed(ApiError):
    status_code = 422
    code = "VALIDATION_FAILED"

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("입력을 확인해 주세요.", fields=fields)


class InvitationInvalid(ApiError):
    status_code = 422
    code = "INVITATION_INVALID"
    def __init__(self) -> None:
        super().__init__("초대 링크가 유효하지 않습니다.")


class InvitationAlreadyHandled(ApiError):
    status_code = 422
    code = "INVITATION_ALREADY_HANDLED"
    def __init__(self) -> None:
        super().__init__("이미 처리된 초대 링크입니다.")


class InvitationExpired(ApiError):
    status_code = 422
    code = "INVITATION_EXPIRED"
    def __init__(self) -> None:
        super().__init__("초대 링크가 만료되었습니다.")


class InvitationMembershipConflict(ApiError):
    status_code = 422
    code = "INVITATION_MEMBERSHIP_CONFLICT"
    def __init__(self) -> None:
        super().__init__("이미 이 동아리에 속해 있습니다.")


class AIUnavailable(ApiError):
    """AIRetryableError/AITimeoutError. 호출 쪽이 잠시 뒤 다시 시도할 수 있다."""

    status_code = 503
    code = "AI_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("AI 응답이 지연되거나 실패했습니다. 잠시 뒤 다시 시도해 주세요.")


class AIMisconfigured(ApiError):
    """AIConfigError. 설정 누락이라 재시도해도 소용없다 — 원문은 서버 로그에만 남긴다."""

    status_code = 500
    code = "AI_MISCONFIGURED"

    def __init__(self) -> None:
        super().__init__("AI 기능을 쓸 수 없는 상태입니다.")


class PlanningStateConflict(ApiError):
    """PlanningStateError (scope_mismatch/draft_mismatch/unsupported_version 등)."""

    status_code = 409
    code = "PLANNING_STATE_CONFLICT"

    def __init__(self) -> None:
        super().__init__("저장된 계획 상태와 맞지 않습니다. 다시 조회한 뒤 시도해 주세요.")



class EventNotPlanning(ApiError):
    """계획 대화·생성은 PLANNING 행사에서만 한다 (FE 명세 v1). 확정 뒤 다시 생성하면
    운영 중 처리한 승인·완료 기록이 지워진다."""

    status_code = 409
    code = "EVENT_NOT_PLANNING"

    def __init__(self) -> None:
        super().__init__("계획 중인 행사에서만 할 수 있습니다.")


class EventNotOnGoing(ApiError):
    """승인·거절·실행 완료·단계 완료는 계획을 확정한 뒤(운영 중)에만 한다 (#177)."""

    status_code = 409
    code = "EVENT_NOT_ON_GOING"

    def __init__(self) -> None:
        super().__init__("운영 중인 행사에서만 처리할 수 있습니다. 계획을 먼저 확정해 주세요.")


class PlanIncomplete(ApiError):
    """행사 시작(계획 확정)에 필요한 값이 빠졌을 때 (POST /events/{id}/start)."""

    status_code = 409
    code = "PLAN_INCOMPLETE"

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("계획 확정에 필요한 값이 없습니다.", fields=fields)


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
