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


# --- events -------------------------------------------------------------


class EventStatus(CodeEnum):
    PLANNING = "PLANNING"
    ON_GOING = "ON_GOING"
    COMPLETE = "COMPLETE"


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


class StepActor(CodeEnum):
    AI = "AI"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    MANUAL = "MANUAL"


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
    PLAN = "PLAN"
    NOTICE = "NOTICE"
    ETC = "ETC"


class RecordFileType(CodeEnum):
    XLSX = "XLSX"
    CSV = "CSV"
    HWP = "HWP"
    PDF = "PDF"
    IMAGE = "IMAGE"


class RecordParseStatus(CodeEnum):
    PARSING = "PARSING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETED = "COMPLETED"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


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
