"""도메인 enum 정의.

DB와 API 모두 같은 문자열 코드를 쓴다. 변환 계층이 없다.

    MemberRole.OWNER            # <MemberRole.OWNER: 'OWNER'>
    MemberRole.OWNER == "OWNER" # True
    MemberRole("OWNER")         # 파싱

값은 추가만 하고, 이미 부여한 값의 의미를 바꾸거나 재사용하지 않는다.
"""

from enum import StrEnum


class CodeEnum(StrEnum):
    """DB 저장값과 API 코드가 같은 문자열 enum."""


# --- auth ---------------------------------------------------------------


class AuthProvider(CodeEnum):
    LOCAL = "LOCAL"
    GOOGLE = "GOOGLE"
    KAKAO = "KAKAO"


# --- clubs --------------------------------------------------------------


class MemberRole(CodeEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    MEMBER = "MEMBER"


class MemberStatus(CodeEnum):
    """가입 승인 상태. 로그인 세션 유효 여부는 Auth.revoked_at이 따로 본다."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"


class ClubCategory(CodeEnum):
    ACADEMIC = "ACADEMIC"
    SPORTS = "SPORTS"
    VOLUNTEER = "VOLUNTEER"
    HOBBY = "HOBBY"
    ETC = "ETC"


# --- events -------------------------------------------------------------


class EventStatus(CodeEnum):
    PLANNING = "PLANNING"
    ON_GOING = "ON_GOING"
    COMPLETE = "COMPLETE"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class EventType(CodeEnum):
    MT = "MT"
    WELCOME = "WELCOME"
    PICNIC = "PICNIC"
    ACADEMIC = "ACADEMIC"
    WORKSHOP = "WORKSHOP"
    ETC = "ETC"


class StepPhase(CodeEnum):
    PREPARATION = "PREPARATION"
    RECRUITING = "RECRUITING"
    EXECUTION = "EXECUTION"
    CANCELLATION = "CANCELLATION"


class StepCode(CodeEnum):
    """고정 단계 카탈로그(#69 step-catalog.md). AI는 이 중에서 고르고 새로 만들지 않는다.

    순서는 각 phase 안에서의 기본 진행 순서와 같다.
    """

    # PREPARATION
    ASSIGN_ROLES = "ASSIGN_ROLES"
    RESEARCH_VENUE = "RESEARCH_VENUE"
    DEMAND_SURVEY = "DEMAND_SURVEY"
    # RECRUITING
    RECRUIT_NOTICE = "RECRUIT_NOTICE"
    CHECK_RESPONSES = "CHECK_RESPONSES"
    CONFIRM_DETAILS = "CONFIRM_DETAILS"
    BOOK_VENUE = "BOOK_VENUE"
    COLLECT_FEES = "COLLECT_FEES"
    # EXECUTION
    PRE_EVENT_NOTICE = "PRE_EVENT_NOTICE"
    EVENT_DAY = "EVENT_DAY"
    SETTLE_EXPENSES = "SETTLE_EXPENSES"
    REFUND_FEES = "REFUND_FEES"
    RECORD_FEEDBACK = "RECORD_FEEDBACK"
    # CANCELLATION (#73)
    CANCEL_NOTIFY_PARTICIPANTS = "CANCEL_NOTIFY_PARTICIPANTS"
    CANCEL_VENUE = "CANCEL_VENUE"
    CANCEL_REFUND = "CANCEL_REFUND"
    CANCEL_RECORD = "CANCEL_RECORD"


class StepActor(CodeEnum):
    AI = "AI"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    MANUAL = "MANUAL"


class StepState(CodeEnum):
    """Step.completed_at으로부터 서버가 계산하는 진행 상태. DB에 저장하지 않는다."""

    DONE = "DONE"
    CURRENT = "CURRENT"
    TODO = "TODO"


class ActionType(CodeEnum):
    EXTERNAL_SEND = "EXTERNAL_SEND"
    TRANSFER = "TRANSFER"
    EXPENSE = "EXPENSE"
    CONTRACT = "CONTRACT"
    NOTICE = "NOTICE"
    CONFIRMATION = "CONFIRMATION"


class ActionStatus(CodeEnum):
    """PENDING → APPROVED → DONE / FAILED, 또는 PENDING → DENIED.

    approve_needed=False인 행동은 APPROVED를 거치지 않고 바로 DONE이 된다.
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    DONE = "DONE"
    FAILED = "FAILED"


# --- records ------------------------------------------------------------


class RecordCategory(CodeEnum):
    LEDGER = "LEDGER"
    ETC = "ETC"
    RULES = "RULES"
    EVENT_HISTORY = "EVENT_HISTORY"


class RecordFileType(CodeEnum):
    XLSX = "XLSX"
    CSV = "CSV"
    HWP = "HWP"
    PDF = "PDF"
    IMAGE = "IMAGE"


class RecordParseStatus(CodeEnum):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETED = "COMPLETED"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class RecordParseErrorReason(CodeEnum):
    """파싱 실패 사유. 화면 문구는 FE가 이 코드로 고르고, 모르는 값은 UNKNOWN으로 본다."""

    COLUMN_MISMATCH = "COLUMN_MISMATCH"
    IMAGE_NOT_READABLE = "IMAGE_NOT_READABLE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    UNKNOWN = "UNKNOWN"


# --- agent --------------------------------------------------------------


class AgentFeature(CodeEnum):
    PLANNING = "PLANNING"
    RETRIEVAL = "RETRIEVAL"
    OPERATIONS = "OPERATIONS"


class AgentRunStatus(CodeEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


# --- chat ---------------------------------------------------------------


class MessageRole(CodeEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
