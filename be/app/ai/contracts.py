"""
BE와 AI 모듈 사이에서 주고받는 요청·응답 데이터 구조를 정의한다.

`contracts.py`는 BE와 AI의 경계를 명확하게 하기 위한 계약이다.
BE는 이 파일에 정의된 Request 객체로 AI를 호출하고,
AI는 정의된 Result/Draft 객체로 결과를 반환한다.

현재: 행사 계획(Planning)기능에 필요한 계약만 정의 

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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import (
    ActionType,
    EventType,
    MessageRole,
    StepActor,
    StepPhase,
)


class ContractModel(BaseModel):
    """
    계약 데이터의 공통 설정 (안전장치)

    frozen=True: 객체를 만든 뒤 변경불가
    extra="forbid": 계약에 없는 필드를 넘기면 실패
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


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
    location_candidates: tuple[str, ...] = ()


class PlanChatRequest(ContractModel):
    """계획 대화 한 턴의 입력"""

    # 다른 행사의 조건·대화가 섞이지 않게 처리 단위를 행사로
    event_id: str
    # 저장된 조건. 이미 정한 값을 다시 묻지 않기 위해 매 호출에 함께 넘긴다
    conditions: EventConditions
    # 시간순 대화. 마지막 항목이 이번 사용자 발화다.
    messages: tuple[ChatTurn, ...] = Field(min_length=1)

    @field_validator("messages")
    @classmethod
    def _end_with_user_turn(cls, value: tuple[ChatTurn, ...]) -> tuple[ChatTurn, ...]:
        """
        계획 대화 요청은 반드시 이번 사용자 발화로 끝나야 한다.

        사용자 발화가 빠진 채 이전 대화만 전달되거나,
        AI 답변을 마지막으로 다시 호출하는 경우를 막는다.
    

        [참고]
        화면에 처음 보이는 인사는 AI 호출 없이 BE가 붙이므로(FE 명세 POST /events)
        이 계약이 받는 대화는 항상 사용자 발화로 끝난다. 이번 발화를 빠뜨리고
        이력만 보내거나 직전 AI 답변이 마지막에 남은 호출을 여기서 거른다.
        AI가 먼저 말을 거는 흐름이 생기면 이 전제부터 다시 본다.
        """
        if value[-1].role != MessageRole.USER:
            raise ValueError("마지막 대화는 사용자 발화여야 합니다")
        return value


class PlanChatResult(ContractModel):
    """계획 대화 한 턴의 결과"""

    # 사용자에게 보여줄 답변. BE가 Message(role=ASSISTANT) 로 저장
    reply: str

    # 이번 대화까지 반영된 행사 조건 전체를 반환한다.
    # 변경된 값만 반환하면, BE가 기존 값을 유지해야 하는지
    # 사용자가 해당 값을 비운 것인지 구분하기 어렵다
    collected: EventConditions

    # 계획안을 만들 만큼 모였는지에 대한 AI의 판단. 권유일 뿐이라 사용자는 무시할 수 있다
    ready_to_generate: bool

    @field_validator("reply")
    @classmethod
    def _require_reply_content(cls, value: str) -> str:
        """AI가 빈 답변을 정상 결과로 반환하지 못하게 한다.

        빈 문자열이나 공백만 있는 답변은 실패와 구분하기 어렵고,
        그대로 저장되면 화면에 빈 메시지가 남을 수 있다.
        """
        if not value.strip():
            raise ValueError("답변 내용이 있어야 합니다")
        return value


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
    started_time: datetime | None = None
    deadline: datetime | None = None

    # 행동이 없는 단계도 있다. 비었다고 완료로 보지 않는다
    actions: tuple[PlannedAction, ...] = ()

    @field_validator("started_time", "deadline")
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
