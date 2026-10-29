"""
BE와 AI 모듈 사이에서 주고받는 요청·응답 데이터 구조를 정의한다.

`contracts.py`는 BE와 AI의 경계를 명확하게 하기 위한 계약이다.
BE는 이 파일에 정의된 Request 객체로 AI를 호출하고,
AI는 정의된 Result/Draft 객체로 결과를 반환한다.

현재: 행사 계획(Planning)과 기록 색인(Retrieval)에 필요한 계약을 정의

주요 원칙:
- BE와 AI는 같은 프로세스 안에서 함수로 호출되므로 필드명은 snake_case를 사용한다.
  외부 API의 camelCase 변환은 BE의 `app/schemas/`에서 처리한다.
- EventType, ActionType 등의 도메인 코드값은 `app.core.enums`를 함께 사용한다.
  BE와 AI에서 같은 enum을 중복 정의하지 않는다.
- 실패를 빈 값으로 돌려주지 않는다. 빈 계획·빈 답변은 호출한 쪽에서 성공과
  구분되지 않으므로 계약에서 막는다(AI-COMMON-02).
- AI는 계획과 행동을 제안만 한다.
  실제 DB 저장, ID 생성, 상태 관리, 권한 확인, 승인 및 실행은 BE가 담당한다.
  따라서 Step/Action ID, 상태값, 승인 여부 등은 이 계약에 포함하지 않는다.
"""

from datetime import date, datetime
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

from pydantic import AfterValidator, BeforeValidator, AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.core.enums import (
    ActionType,
    EventType,
    MessageRole,
    RecordFileType,
    StepActor,
    StepPhase,
    StepCode,
)

from .llm import EMBEDDING_DIMENSIONS
from .errors import PlanningStateError
from .planning_catalog import PLANNING_STEP_NAMES


# 공통 계약 기반

class ContractModel(BaseModel):
    """
    계약 데이터의 공통 설정 (안전장치)

    frozen=True: 객체를 만든 뒤 변경불가
    extra="forbid": 계약에 없는 필드를 넘기면 실패
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_text(value: str) -> str:
    if not value.strip():
        raise ValueError("내용이 있어야 합니다")
    return value


# 공백만 있는 문자열은 빈 값과 같아 막는다
NonBlankStr = Annotated[str, AfterValidator(_require_text)]


# 검색과 기존 생성에서 공유하는 대화 및 행사 조건

class ChatTurn(ContractModel):
    """
    대화 한 번. BE가 `Message` 행에서 만들어 시간순으로 넘긴다
    """

    # SYSTEM 은 BE가 넘기지 않지만 enum을 좁히면 Message.role 과 목록이 갈린다.
    role: MessageRole
    content: str


class EventConditions(ContractModel):
    """
    행사 조건. 정해지지 않은 항목은 `None`
    필드는 `Event` 모델의 계획 관련 컬럼과 1:1

    현재까지 정해진 행사 조건의 스냅샷

    """

    event_type: EventType | None = None
    start_date: date | None = None
    end_date: date | None = None
    headcount: int | None = Field(default=None, ge=1)
    # 금액은 정수 원 단위로만 다룬다
    budget_total: int | None = Field(default=None, ge=0)
    fee_per_person: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=200)


# 기존 계획 생성 계약 (P1 공개 계약과 별도)

class PlannedAction(ContractModel):
    """Step 안에서 실제로 수행할 수 있는 행동 하나.

    예:
    - 참가 신청 열기
    - 입금 확인하기
    - 안내 메시지 보내기

    AI는 필요한 Action만 제안한다.
    실제 Action 생성, 상태 관리, 승인 및 실행은 BE가 담당한다.
    """

    # 지원하는 여섯 가지 밖의 일은 제안하지 않고 사람이 할 일로 안내
    type: ActionType
    title: str = Field(max_length=200)
    subtitle: str | None = None
    amount: int | None = Field(default=None, ge=0)
    due_date: date | None = None


class PlannedStep(ContractModel):
    """행사 계획을 구성하는 업무 단계 하나.

    하나의 Step 안에는 여러 Action이 포함될 수 있다.

    예:
    Step: 참가자 모집 관리
      - Action: 참가 신청 열기
      - Action: 입금 확인하기

    steps 목록의 순서가 실제 진행 순서다.
    Step ID와 순서는 계획을 저장할 때 BE가 생성한다.
    """

    # 세 묶음으로 나눠 보여준다. 묶기는 BE가 이 값으로 한다(FE 명세 phases[]).
    phase: StepPhase
    name: str = Field(max_length=100)

    # 이 Step을 누가 처리하는지 나타낸다.
    # 예: 자동 처리 / 운영진 승인 필요 / 운영진 직접 수행
    actor: StepActor

    # Step 시작 시각과 마감 시각.
    # 아직 정해지지 않았다면 None으로 둔다.
    starts_at: datetime | None = None
    deadline: datetime | None = None

    # 행동이 없는 단계도 있다. 비었다고 완료로 보지 않는다
    actions: tuple[PlannedAction, ...] = ()

    @field_validator("starts_at", "deadline")
    @classmethod
    def _require_timezone(cls, value: datetime | None) -> datetime | None:
        """시각에는 반드시 시간대 정보를 포함하도록 한다.

        BE와 FE가 서로 다른 시간대로 해석하는 문제를 방지한다.
        """
        if value is not None and value.tzinfo is None:
            raise ValueError("시간대가 있는 값이어야 합니다")
        return value


class ExcludedStep(ContractModel):
    """보통 두는데 이번 계획에서 뺀 단계와 그 이유

    `reason`은 AI가 쓰는 문장
    """

    name: str = Field(max_length=100)
    reason: str


class PlanGenerateRequest(ContractModel):
    """계획안 생성의 입력"""

    event_id: str

    # 지금까지 확정된 행사 조건
    conditions: EventConditions

    # 행사 조건만으로는 알 수 없는 사용자 요구사항이나 맥락을 참고하기 위해
    # 계획 대화 내역도 함께 전달한다.
    messages: tuple[ChatTurn, ...] = ()


class PlanDraft(ContractModel):
    """생성된 계획안

    AI가 만들어서 반환하는 행사 계획 초안 전체
    단계 수·담당별 개수 같은 요약값은 세면 나오므로 담지 않는다. BE가 계산한다.
    """

    # AI가 제안한 행사 진행 단계 목록
    # 단계가 없으면 화면에 보여줄 것도, 확정 후 운영을 시작할 근거도 없다.
    # 운영 시작에는 시작일과 단계 하나가 필요하다
    steps: tuple[PlannedStep, ...] = Field(min_length=1)

    # AI가 짚은 문장 경고
    warnings: tuple[str, ...] = ()
    excluded_steps: tuple[ExcludedStep, ...] = ()


# 기록 색인 계약


class SourceLocation(ContractModel):
    """원문 위치. FE 명세 `sources[].location`과 같다

    나중에 page·sheet 같은 필드를 더할 수 있게 객체로 둔다
    """

    # 화면에 보이는 위치. 예: "예산 항목", "회비 수납 시트"
    label: NonBlankStr


class RecordBlock(ContractModel):
    """BE가 파싱한 텍스트 블록 하나 (parse_result의 항목)"""

    text: NonBlankStr
    location: SourceLocation


class IndexRecordRequest(ContractModel):
    """기록 색인의 입력

    club_id·event_id·category는 받지 않는다. 청크에 붙여 저장하는 일은 BE가 한다
    """

    # 오류, 로그에서 기록을 가리키는 용도
    record_id: str
    # 임베딩할 때 청크 앞에 붙여 연도, 행사명으로도 찾게 한다
    file_name: str = Field(max_length=255)
    # None이면 파일 없는 텍스트 기록이며 문서로 처리한다
    file_type: RecordFileType | None
    # 순서가 블록 번호(0부터)다. 비어 있으면 index_record가 AIEmptyRecordError를 올린다
    blocks: tuple[RecordBlock, ...]


class IndexedChunk(ContractModel):
    """검색 단위인 청크 하나. 메타데이터는 BE가 저장할 때 붙인다"""

    # 원문. 문서명은 임베딩할 때만 붙인다
    text: NonBlankStr
    location: SourceLocation
    # 이 청크가 나온 원본 블록 번호. 위치로 원문을 다시 찾기 위해 둔다
    block_indexes: tuple[Annotated[int, Field(ge=0)], ...] = Field(min_length=1)
    # 차원이 다르면 DB 컬럼 vector(1536)에 저장할 수 없다
    embedding: tuple[float, ...] = Field(
        min_length=EMBEDDING_DIMENSIONS, max_length=EMBEDDING_DIMENSIONS
    )


class IndexRecordResult(ContractModel):
    """기록 색인의 결과"""

    # 빈 결과를 성공으로 돌려주지 않는다
    chunks: tuple[IndexedChunk, ...] = Field(min_length=1)


class RecordSource(ContractModel):
    """답변·근거의 출처. FE 명세 `sources[]`와 1:1"""

    record_id: str
    file_name: str
    location: SourceLocation


# 기록 검색 결과 계약

class RecordFact(ContractModel):
    """기록에서 확인한 사실 하나와 그 내용이 적힌 출처"""

    content: NonBlankStr
    # 검색된 청크의 출처만 들어간다. 출처 없는 사실은 사실로 내지 않는다
    sources: tuple[RecordSource, ...] = Field(min_length=1)


class RecordConflict(ContractModel):
    """같은 사실에 대해 자료끼리 값이 다른 경우. 하나를 고르지 않고 출처별 값을 둔다"""

    # 무엇이 다른지. 예: "2025 봄 MT 참가 인원"
    description: NonBlankStr
    values: tuple[RecordFact, ...] = Field(min_length=2)


class RecordSearchResult(ContractModel):
    """기록 검색 결과. 관련 기록이 없는 것도 정상 결과다"""

    facts: tuple[RecordFact, ...] = ()
    # 찾는 내용 중 기록에서 확인하지 못한 것. 예: "예비비 사용처"
    not_found: tuple[NonBlankStr, ...] = ()
    conflicts: tuple[RecordConflict, ...] = ()

    @model_validator(mode="after")
    def _report_not_found(self) -> "RecordSearchResult":
        """아무것도 담지 않은 결과는 실패와 구분되지 않으므로 막는다(AI-COMMON-02)"""
        if not (self.facts or self.conflicts or self.not_found):
            raise ValueError("찾은 사실이 없으면 확인하지 못한 것을 적어야 합니다")
        return self


# P1 행사 조건과 발화 근거

def _require_calendar_date(value: object) -> object:
    """timestamp/datetime의 날짜 변환과 불완전한 날짜의 묵시적 보정을 막는다."""
    if isinstance(value, datetime):
        raise ValueError("시각이 아닌 날짜를 입력해야 합니다")
    if isinstance(value, date):
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return date.fromisoformat(value)
    raise ValueError("날짜는 date 또는 YYYY-MM-DD 형식이어야 합니다")


CalendarDate = Annotated[date, BeforeValidator(_require_calendar_date)]


Headcount = Annotated[int, Field(strict=True, ge=1)]


Won = Annotated[int, Field(strict=True, ge=0)]


class PlanningConditions(ContractModel):
    """사용자가 정한 행사 조건의 불변 스냅샷. None은 미정, 0원은 무료다.

    과거 기록·AI 제안·복수 후보는 이 객체에 자동 병합하지 않는다.
    이 타입은 값의 형식만 검증하며 사용자 수락 여부는 추출 단계가 판단한다.
    BE 저장 모델이 아니므로 title 미정을 허용한다.
    """

    title: str | None = Field(default=None, max_length=100)
    event_type: EventType | None = None
    headcount: Headcount | None = None
    fee_per_person: Won | None = None
    start_date: CalendarDate | None = None
    end_date: CalendarDate | None = None
    location: str | None = Field(default=None, max_length=200)
    # 명시한 예산 상한만 보관한다. 참가비나 합계를 계산하지 않는다.
    budget_total: Won | None = None

    @field_validator("title", "location")
    @classmethod
    def _require_nonblank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("미정은 null로 표현하고 공백만 입력할 수 없습니다")
        return value

    @model_validator(mode="after")
    def _require_ordered_dates(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("종료일은 시작일보다 빠를 수 없습니다")
        return self


ConditionField = Literal[
    "title", "event_type", "headcount", "fee_per_person", "start_date",
    "end_date", "location", "budget_total",
]


class MessageEvidence(ContractModel):
    message_id: NonBlankStr
    quote: NonBlankStr


# P1 조건의 잠정 여부와 보류 상태

ConditionStatus = Literal["tentative", "specified"]
PlanningTopic = Literal[
    "title", "event_type", "headcount", "fee_per_person", "dates", "location", "budget_total",
]


def topic_for(field: ConditionField) -> PlanningTopic:
    """시작일·종료일은 함께 의논하는 날짜 주제로 취급한다."""
    return "dates" if field in {"start_date", "end_date"} else field


class ConditionMeta(ContractModel):
    """값을 얼마나 정해 두었는지와 근거. specified도 최종 승인은 아니다."""

    status: ConditionStatus
    evidence: MessageEvidence


class PlanningDraft(ContractModel):
    """조건 값·부가정보·보류를 함께 반환하는 초안. BE 저장 모델이 아니다.

    frozen은 내부 dict까지 잠그지 않는다. 처리기는 복사본으로 작업하고
    새 PlanningDraft를 검증해 반환하며, 입력의 condition_meta를 수정하지 않는다.
    """

    conditions: PlanningConditions = Field(default_factory=PlanningConditions)
    condition_meta: dict[ConditionField, ConditionMeta] = Field(default_factory=dict)
    deferred_topics: tuple[PlanningTopic, ...] = () #보류한 부분

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if any(getattr(self.conditions, field) is None for field in self.condition_meta):
            raise ValueError("미정인 조건에는 잠정/명시 메타정보를 붙일 수 없습니다")
        if len(self.deferred_topics) != len(set(self.deferred_topics)):
            raise ValueError("보류 주제는 중복될 수 없습니다")
        return self


# P1 과거 기록 조회 결과

class RecordLookupResult(ContractModel):
    status: Literal["available", "not_found", "failed", "rejected"]
    query: str | None = None
    result: RecordSearchResult | None = None
    reason: NonBlankStr | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status in {"available", "not_found"}:
            if self.result is None or not self.query:
                raise ValueError("검색 성공에는 질문과 검색 결과가 필요합니다")
            found = bool(self.result.facts or self.result.conflicts)
            if found != (self.status == "available"):
                raise ValueError("검색 상태와 근거 유무가 다릅니다")
        elif self.result is not None or self.reason is None:
            raise ValueError("검색 실패·거절에는 근거 대신 이유가 필요합니다")
        return self


# P1 생성 요청 근거와 계획 초안

def valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("유효한 IANA 시간대가 필요합니다") from error
    return value


class ChatGenerationTrigger(ContractModel):
    source: Literal["chat"] = "chat"
    request_id: NonBlankStr  # 이번 사용자 메시지 ID
    quote: NonBlankStr


class ButtonGenerationTrigger(ContractModel):
    source: Literal["button"] = "button"
    request_id: NonBlankStr  # 호출자가 만든 클릭 요청 ID. 채팅 근거를 요구하지 않는다.


class PlanAction(ContractModel):
    type: ActionType
    title: NonBlankStr
    due_date: CalendarDate | None = None


class PlanStepFields(ContractModel):
    code: StepCode
    purpose: NonBlankStr
    starts_at: AwareDatetime | None = None
    deadline: AwareDatetime | None = None
    actions: tuple[PlanAction, ...] = ()


class ExcludedPlanStep(ContractModel):
    code: StepCode
    reason: NonBlankStr


class ExcludedPreviewStep(ExcludedPlanStep):
    """최종 제외 단계. LLM 출력과 달리 카탈로그 이름을 포함한다."""

    name: NonBlankStr

    @model_validator(mode="before")
    @classmethod
    def restore_missing_name(cls, value):
        # 이전 저장 상태에는 name이 없다. 모델 재호출 없이 파생 정보만 보완한다.
        # 전달받은 dict를 직접 고치지 않아 BE가 읽어 온 원본 상태도 보존한다.
        if isinstance(value, dict) and "name" not in value:
            code = value.get("code")
            name = PLANNING_STEP_NAMES.get(code) if isinstance(code, str) else None
            if name is not None:
                return {**value, "name": name}
        return value

    @model_validator(mode="after")
    def validate_catalog_name(self) -> Self:
        if self.name != PLANNING_STEP_NAMES.get(self.code):
            raise ValueError("제외 단계 이름이 계획 카탈로그와 다릅니다")
        return self


class PreviewStep(PlanStepFields):
    name: NonBlankStr
    phase: StepPhase
    actor: StepActor


class PlanAssumption(ContractModel):
    content: NonBlankStr
    sources: tuple[RecordSource, ...] = ()


# 실제로 생성한 단계별 계획 ex. 장소조사 -> 모집 공지 -> 행사 진행
class EventPlanPreview(ContractModel):
    id: NonBlankStr  # 로컬에서 참조할 임시 ID. BE의 Step/Plan ID가 아니다.
    basis_draft: PlanningDraft
    trigger: ChatGenerationTrigger | ButtonGenerationTrigger
    steps: tuple[PreviewStep, ...] = Field(min_length=1)
    excluded_steps: tuple[ExcludedPreviewStep, ...]
    assumptions: tuple[PlanAssumption, ...] = ()
    open_questions: tuple[NonBlankStr, ...] = ()
    warnings: tuple[NonBlankStr, ...] = ()


class PlanGenerationResult(ContractModel):
    status: Literal["generated", "needs_clarification", "failed"]
    preview: EventPlanPreview | None = None
    reason: NonBlankStr | None = None
    model_calls: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status == "generated":
            if self.preview is None or self.reason is not None:
                raise ValueError("생성 성공에는 계획 초안만 필요합니다")
        elif self.preview is not None or self.reason is None:
            raise ValueError("생성 보류·실패에는 이유만 필요합니다")
        return self


# AI가 생성 권할때 어떤 조건으로 권했는지 (날짜 없이 준비 순서를 만들어본다던지)
class GenerationOffer(ContractModel):
    id: NonBlankStr #나중에 사용자가 무엇을 수락했는지 연결할 제안 번호
    status: Literal["pending", "deferred"] #아직 수락하거나 보류하지 않은 제안
    summary: NonBlankStr # 무엇을 만들자는 제안인지
    basis_draft: PlanningDraft # 권유 당시의 행사 조건 복사본


class PlanningGenerationState(ContractModel):
    offer: GenerationOffer | None = None
    preview: EventPlanPreview | None = None
    # 거절된 조건 변경이 남으면 옛 값으로 조용히 생성하지 않는다.
    condition_change_pending: bool = False
    pending_condition_fields: tuple[ConditionField, ...] = ()

    @model_validator(mode="after")
    def _pending_fields(self) -> Self:
        if self.pending_condition_fields and not self.condition_change_pending:
            raise ValueError("미해결 조건 필드가 있으면 변경 확인도 필요합니다")
        return self


# P1 대화를 이어가기 위한 저장 상태

MAX_PLANNING_HISTORY = 60
# 모델 품질 기준이 아닌 초기 안내 정책이다. 남은 사용자 턴 수로 환산하지 않는다.
PLANNING_HISTORY_WARNING_THRESHOLD = MAX_PLANNING_HISTORY * 4 // 5


class PlanningStoredToolCall(ContractModel):
    id: NonBlankStr
    name: NonBlankStr
    args: dict[str, JsonValue]


class PlanningStoredMessage(ContractModel):
    role: Literal['user', 'assistant', 'tool']
    id: NonBlankStr | None = None
    content: str | list[str | dict[str, JsonValue]]
    tool_calls: tuple[PlanningStoredToolCall, ...] = ()
    name: NonBlankStr | None = None
    tool_call_id: NonBlankStr | None = None
    tool_status: Literal['success', 'error'] | None = None

    @model_validator(mode='after')
    def validate_role(self) -> Self:
        if self.role != 'assistant' and self.tool_calls:
            raise ValueError('Tool 호출은 assistant 메시지에만 가능합니다')
        if self.role == 'tool':
            if self.tool_call_id is None or self.tool_status is None:
                raise ValueError('Tool 결과에는 호출 ID와 상태가 필요합니다')
        elif self.tool_call_id is not None or self.tool_status is not None:
            raise ValueError('Tool 결과 필드는 tool 메시지에만 가능합니다')
        return self


class PlanningStatePayload(ContractModel):
    basis_draft: PlanningDraft
    history: tuple[PlanningStoredMessage, ...] = Field(default=(), max_length=MAX_PLANNING_HISTORY)
    generation: PlanningGenerationState = Field(default_factory=PlanningGenerationState)

    @model_validator(mode='after')
    def validate_pairs(self) -> Self:
        # AI의 호출과 Tool 결과가 하나의 묶음이어야 다음 모델 호출이 가능하다.
        pending: set[str] = set()
        seen: set[str] = set()
        message_ids: set[str] = set()
        for message in self.history:
            if message.id is not None:
                if message.id in message_ids:
                    raise ValueError('메시지 ID가 중복되었습니다')
                message_ids.add(message.id)
            if message.role == 'tool':
                if message.tool_call_id not in pending:
                    raise ValueError('대응하는 Tool 호출이 없습니다')
                pending.remove(message.tool_call_id)
                continue
            if pending:
                raise ValueError('Tool 호출 뒤 실행 결과가 필요합니다')
            for call in message.tool_calls:
                if call.id in seen:
                    raise ValueError('Tool 호출 ID가 중복되었습니다')
                seen.add(call.id)
                pending.add(call.id)
        if pending:
            raise ValueError('실행 결과가 없는 Tool 호출입니다')
        return self


class PlanningResumeState(ContractModel):
    schema_version: Literal[1] = 1
    club_id: NonBlankStr
    event_id: NonBlankStr
    conversation_id: NonBlankStr
    payload: PlanningStatePayload

    @field_validator('schema_version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise PlanningStateError('unsupported_version', '지원하지 않는 계획 상태 버전입니다')
        return value


# P1 채팅과 버튼 요청

class PlanningUserMessage(ContractModel):
    id: NonBlankStr
    content: Annotated[NonBlankStr, Field(max_length=4000)]


class PlanningRequestContext(ContractModel):
    request_id: NonBlankStr
    club_id: NonBlankStr
    event_id: NonBlankStr
    conversation_id: NonBlankStr
    base_revision: Annotated[int, Field(strict=True, ge=0)]
    draft: PlanningDraft
    resume_state: PlanningResumeState | None = None
    reference_date: CalendarDate
    timezone: NonBlankStr = 'Asia/Seoul'

    _timezone = field_validator('timezone')(valid_timezone)

    @model_validator(mode='after')
    def validate_resume(self) -> Self:
        state = self.resume_state
        if state is not None:
            if (self.club_id, self.event_id, self.conversation_id) != (
                state.club_id, state.event_id, state.conversation_id,
            ):
                raise PlanningStateError('scope_mismatch', '다른 행사 또는 대화의 상태입니다')
            if self.draft != state.payload.basis_draft:
                raise PlanningStateError('draft_mismatch', '조건과 대화 상태의 동기화가 필요합니다')
        return self


# 현재 조건과 사용자 메시지를 전달 BE -> AI에 보낼 내용을 담
class PlanningChatRequest(PlanningRequestContext):
    message: PlanningUserMessage

    @model_validator(mode='after')
    def validate_new_message(self) -> Self:
        if self.resume_state and any(
            m.id == self.message.id for m in self.resume_state.payload.history
        ):
            raise ValueError('이번 메시지가 이미 이력에 있습니다')
        return self

# 버튼으로 초안 요청하는 입력
class PlanningPreviewRequest(PlanningRequestContext):
    use_current_conditions: bool = False


# P1 화면용 결과와 다음 보관 상태

class PlanningGenerationReadiness(ContractModel):
    can_generate: bool
    reasons: tuple[Literal['event_type_missing', 'condition_change_pending'], ...] = ()

    @model_validator(mode='after')
    def validate_reasons(self) -> Self:
        if self.can_generate == bool(self.reasons):
            raise ValueError('생성 가능 여부와 차단 사유가 일치하지 않습니다')
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError('차단 사유가 중복되었습니다')
        return self


class PlanningHistoryUsage(ContractModel):
    """화면에 전달할 이력 정보. 사용자/AI/Tool 메시지를 같은 기준으로 센다."""

    message_count: Annotated[int, Field(strict=True, ge=0, le=MAX_PLANNING_HISTORY)]
    max_messages: Literal[60] = MAX_PLANNING_HISTORY
    near_limit: bool

    @classmethod
    def from_count(cls, message_count: int) -> Self:
        return cls(message_count=message_count,
                   near_limit=message_count >= PLANNING_HISTORY_WARNING_THRESHOLD)

    @model_validator(mode="after")
    def validate_usage(self) -> Self:
        if self.near_limit != (self.message_count >= PLANNING_HISTORY_WARNING_THRESHOLD):
            raise ValueError("이력 사용량과 한도 임박 여부가 다릅니다")
        return self


class PlanningView(ContractModel):
    reply: NonBlankStr | None = None
    draft: PlanningDraft
    changed_fields: tuple[ConditionField, ...] = ()
    record_lookup: RecordLookupResult | None = None
    generation_readiness: PlanningGenerationReadiness
    generation_result: PlanGenerationResult | None = None
    preview_is_current: bool = False
    # 이전에 저장한 화면 응답은 정보 없음으로 읽는다. 0개라고 추정하지 않는다.
    history_usage: PlanningHistoryUsage | None = None

# 화면용 결과와 보관용 상태
class PlanningPublicResult(ContractModel):
    request_id: NonBlankStr
    base_revision: Annotated[int, Field(strict=True, ge=0)]
    view: PlanningView
    next_state: PlanningResumeState

    @model_validator(mode='after')
    def validate_snapshot(self) -> Self:
        if self.view.draft != self.next_state.payload.basis_draft:
            raise ValueError('화면 조건과 보관 상태의 조건이 다릅니다')
        if self.view.history_usage is not None:
            if self.view.history_usage.message_count != len(self.next_state.payload.history):
                raise ValueError('화면 이력 사용량과 보관 상태의 이력이 다릅니다')
        return self
