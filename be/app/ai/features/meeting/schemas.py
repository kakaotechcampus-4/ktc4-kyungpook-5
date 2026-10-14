"""회의 발화 판단에 필요한 데이터 형식을 정의한다.

요청·결과 타입은 docs/contracts.md "회의 발화 처리 초안"(#113)과 같은 모양이다.
BE와 합의하기 전이라 contracts.py에 두지 않고, 합의하면 contracts.py와 ports.py로 옮긴다.
"""

from datetime import date
from typing import Literal, Protocol, Self

from pydantic import AwareDatetime, Field, model_validator

from app.core.enums import EventType

from ...contracts import ContractModel, NonBlankStr, RecordSource
from ...ports import RetrievedChunk


# 판단 모델이 직접 만드는 값. 나머지 결과는 코드가 채운다.
# 이유·확신도를 받으면 판단이 0.65초 느려져 두 칸만 받는다(#111).
# docstring을 달지 않는다. 출력 스키마의 description으로 모델에 그대로 전달되어
# 측정 때와 다른 입력이 된다.
class JudgeOutput(ContractModel):
    needs_lookup: bool
    # needs_lookup이 false면 빈 문자열이다. 검색어이자 화면의 "무엇을 물었는지" 문구다
    query: str


class MeetingUtterance(ContractModel):
    """발화 하나. BE가 VAD 구간을 Whisper로 바꾼 확정 전사다"""

    utterance_id: str
    # 회의 안에서 1부터 하나씩 커진다. 재연결해도 이어진다
    seq: int = Field(ge=1)
    # 같은 발화의 전사가 고쳐지면 커진다. 결과의 source_version으로 그대로 돌려준다
    version: int = Field(default=1, ge=1)
    # AI는 고치지 않는다. 오인식 보정은 검색 후보에만 한다
    text: NonBlankStr
    # 시간대가 없으면 회의 날짜를 한국 날짜로 바꿀 수 없어 받지 않는다
    started_at: AwareDatetime
    ended_at: AwareDatetime

    @model_validator(mode="after")
    def _ends_after_start(self) -> Self:
        if self.ended_at < self.started_at:
            raise ValueError("발화 끝 시각이 시작 시각보다 앞설 수 없습니다")
        return self


class MeetingEvent(ContractModel):
    """회의가 특정 행사에 묶여 있을 때 그 행사. 검색어를 만들 때 참고한다"""

    event_id: str
    # 예: "2026 봄 MT"
    title: NonBlankStr
    event_type: EventType | None = None
    start_date: date | None = None


class JudgeUtteranceRequest(ContractModel):
    """발화 하나의 판단 요청"""

    meeting_id: str
    # 이 회의가 볼 수 있는 기록 범위. BE가 권한을 확인한 값이며 넓히지 않는다
    club_id: str
    utterance: MeetingUtterance
    # 바로 앞 발화들. 오래된 것부터. 판단에는 마지막 MEETING_CONTEXT_UTTERANCES개만 쓴다
    context: tuple[MeetingUtterance, ...] = ()
    # 회의를 행사에 묶지 않았으면 None
    event: MeetingEvent | None = None

    @model_validator(mode="after")
    def _context_comes_before(self) -> Self:
        """앞 발화가 순번 순서로, 이번 발화보다 앞에 있어야 한다.

        순서가 섞이면 "그때"가 가리키는 대상을 잘못 풀어 검색어가 틀어진다.
        """
        seqs = [item.seq for item in self.context] + [self.utterance.seq]
        if any(before >= after for before, after in zip(seqs, seqs[1:])):
            raise ValueError("앞 발화는 순번 순서여야 하고 이번 발화보다 앞서야 합니다")
        return self


# 판단 뒤 AI가 부르는 도구. records.search는 기록 검색, llm.generate는 답 작성이다
ToolName = Literal["records.search", "llm.generate"]


class ToolCall(ContractModel):
    """판단 뒤 AI가 실제로 부른 도구 하나"""

    tool: ToolName
    # 예: 검색어 "2025 봄 MT 숙소비"
    input: str
    status: Literal["OK", "FAILED", "TIMEOUT"]
    duration_ms: int = Field(ge=0)
    # records.search일 때 찾은 조각 수
    result_count: int | None = Field(default=None, ge=0)


class JudgeTrace(ContractModel):
    """이 판단을 어떤 모델과 지시로 내렸고 무엇을 했는지. BE가 판단 기록으로 저장한다

    모두 모델 출력이 아니라 코드가 채운다. 판단 지연에 영향이 없다.
    """

    # 예: "gpt-5.6-luna". AI_MODEL 설정값
    model: str
    # 예: "meeting-judge-v5". 프롬프트 원문을 바꾸면 올린다
    prompt_version: str
    # 판단(과 검색어) 호출에 걸린 시간
    judge_ms: int = Field(ge=0)
    # NONE이면 비어 있다
    tool_calls: tuple[ToolCall, ...] = ()


# 어떤 처리로 갔는지. 지금은 RAG(기록 조회)와 NONE뿐이고 나중에 LLM이 추가된다(#124)
Route = Literal["RAG", "NONE"]


# 조회하지 않은 이유. route가 NONE일 때만 쓰고 RAG면 검색어가 곧 이유라 비운다.
# 실시간 결과에는 넣지 않는다. 이유를 출력하게 하면 판단이 느려진다(#111).
# 회의 뒤 다시 판단하거나 사람이 검수할 때 채운다(#117).
# 앞의 다섯은 prompts/judge.md의 "조회가 필요 없는 경우"와 같은 순서로 하나씩 맞춘다.
#   CURRENT_STATUS      기록에 없는 지금 일을 묻는 말    "민수야 예약했어?"
#   MONOLOGUE           혼잣말·감탄                      "이게 맞나"
#   CHITCHAT            기록과 무관한 잡담·부탁          "점심 뭐 먹지?", "화면 좀 넘겨 줄래?"
#   FUTURE_DECISION     앞으로 할 일을 정하는 말         "이번엔 버스 대절하죠"
#   REFERENCE_MATERIAL  과거 자료를 같이 보자는 말       "작년 축제 자료 펴 놓고 얘기해요"
#   NEEDS_CONTEXT       가리키는 대상을 아직 알 수 없음  "그거 얼마였지?" (앞에 대상이 없음)
#   OTHER               어디에도 맞지 않음. 자주 나오면 코드를 늘린다
# 사람을 불렀는지는 기준이 아니다. "민수야, 작년 회칙상 환불 기준이 뭐였지?"는 RAG다(AI-MEET-01).
# REFERENCE_MATERIAL은 값을 묻지 않아 값으로 답하지 않을 뿐이다. 이 코드가 붙은 발화 수로
# 문서 제목과 열기 링크를 띄우는 record_reference를 만들지 정한다(docs/architecture.md).
ReasonCode = Literal[
    "CURRENT_STATUS",
    "MONOLOGUE",
    "CHITCHAT",
    "FUTURE_DECISION",
    "REFERENCE_MATERIAL",
    "NEEDS_CONTEXT",
    "OTHER",
]


class JudgeUtteranceResult(ContractModel):
    """발화 하나의 판단 결과"""

    utterance_id: str
    # 판단에 쓴 전사 버전. 전사가 고쳐지면 BE가 옛 판단을 STALE로 가려낸다
    source_version: int = Field(ge=1)
    route: Route
    kind: Literal["NO_LOOKUP", "ANSWER", "NOT_FOUND"]
    # 무엇에 대한 답인지. 검색어 구성 단계가 만든 검색어(보정 전)다. NO_LOOKUP이면 None
    question: NonBlankStr | None = None
    # ANSWER일 때만
    answer: NonBlankStr | None = None
    # ANSWER일 때 하나 이상
    sources: tuple[RecordSource, ...] = ()
    trace: JudgeTrace

    @model_validator(mode="after")
    def _kind_matches_fields(self) -> Self:
        """kind마다 있어야 할 값을 강제한다.

        빈 답이나 출처 없는 답이 정상 결과로 나가면 "기록에 없음"과 구분되지 않는다(AI-MEET-07).
        """
        if self.kind == "NO_LOOKUP":
            if self.route != "NONE":
                raise ValueError("NO_LOOKUP은 route가 NONE이어야 합니다")
            if self.question or self.answer or self.sources or self.trace.tool_calls:
                raise ValueError("NO_LOOKUP에는 질문·답·출처·도구 호출이 없어야 합니다")
            return self

        if self.route != "RAG":
            raise ValueError("ANSWER·NOT_FOUND는 route가 RAG여야 합니다")
        if self.question is None:
            raise ValueError("조회한 결과에는 무엇을 물었는지가 있어야 합니다")
        if self.kind == "ANSWER" and (self.answer is None or not self.sources):
            raise ValueError("ANSWER에는 답과 출처가 하나 이상 있어야 합니다")
        if self.kind == "NOT_FOUND" and (self.answer is not None or self.sources):
            raise ValueError("NOT_FOUND에는 답과 출처가 없어야 합니다")
        return self


class JudgeReview(ContractModel):
    """사람이 판단 하나를 보고 붙인 정답. Laya 학습 데이터의 정답이 된다(#117)

    판단 기록(BE의 context-decisions)에 넣지 않고 그 id를 가리키는 별도 기록으로 둔다.
    제품 화면이 쓰는 값이 아니라 학습 데이터이기 때문이다. 저장 위치는 BE와 정한다.
    경계 사례는 두 명 이상이 보므로 판단 하나에 검수 기록이 여러 개 붙을 수 있다.
    """

    # 검수한 판단 기록의 id
    decision_id: NonBlankStr
    # 사람이 정한 정답. 모델이 낸 route가 아니다
    label: Route
    # label이 NONE일 때만 채운다. 정할 수 없으면 OTHER
    reason_code: ReasonCode | None = None
    # 검수자를 가리키는 id. 실명을 넣지 않는다
    reviewer: NonBlankStr
    # 모델의 판단을 가리고 붙였는지. 가린 라벨과 보여준 라벨의 일치율을 비교해
    # 검수가 모델 답에 끌려가는지 본다
    blind: bool
    reviewed_at: AwareDatetime
    # 형식 버전. 칸을 바꾸면 올리고, 이전 버전을 읽는 변환을 이 파일에 함께 둔다
    schema_version: Literal[1] = 1

    @model_validator(mode="after")
    def _reason_matches_label(self) -> Self:
        """이유는 NONE에만 있다. RAG는 검색어가 곧 이유다"""
        if self.label == "NONE" and self.reason_code is None:
            raise ValueError("NONE으로 검수했으면 조회하지 않은 이유를 골라야 합니다")
        if self.label == "RAG" and self.reason_code is not None:
            raise ValueError("RAG로 검수했으면 조회하지 않은 이유를 비워야 합니다")
        return self


class MeetingAnswer(ContractModel):
    """찾은 기록으로 쓴 답. 출처는 검색된 조각에서 옮긴 것이어야 한다"""

    answer: NonBlankStr
    sources: tuple[RecordSource, ...] = Field(min_length=1)


class RecordLookup(Protocol):
    """판단 뒤 기록을 찾아 답을 쓰는 단계. 기록 검색(#72)이 생기면 그 위에 구현한다

    단계를 둘로 나눈 것은 처리 단계(SEARCHING·ANSWERING)와 도구 호출 기록을
    판단 노드가 한곳에서 남기기 위해서다.
    """

    async def search(
        self, club_id: str, question: str
    ) -> tuple[RetrievedChunk, ...]:
        """질문과 비슷한 조각을 찾는다. 없으면 빈 튜플이며 실패가 아니다"""
        ...

    async def answer(
        self, question: str, chunks: tuple[RetrievedChunk, ...]
    ) -> MeetingAnswer | None:
        """찾은 조각으로 답을 쓴다. 조각에 답이 없으면 None이다"""
        ...


# 처리 단계. 화면의 진행 표시(activity)에 쓴다
MeetingStage = Literal["JUDGING", "SEARCHING", "ANSWERING"]


class MeetingProgressPort(Protocol):
    """단계가 바뀔 때 AI가 알린다. 구현체는 BE가 주입한다"""

    async def stage_changed(self, utterance_id: str, stage: MeetingStage) -> None: ...
