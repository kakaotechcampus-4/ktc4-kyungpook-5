# BE-AI 데이터 계약 (contracts.py)

## 무엇인가

[`contracts.py`](../contracts.py)는 BE와 AI 모듈이 같은 프로세스 안에서 주고받는
요청·결과의 형식을 정의한다. DB 모델이나 FE 공개 API 스키마가 아니라,
`app.ai` 경계를 위한 내부 계약이다.

행사 계획(조건 수집·계획안 생성)과 기록 색인에 필요한 타입을 정의한다.
기록 색인은 `app.ai.index_record`로 호출하고, 계획 공개 함수는 BE와 합의한 뒤 제공한다.
회의 발화 처리는 #113에서 합의할 AI 초안을 [아래](#회의-발화-처리-초안)에 둔다.

## 왜 필요한가

- BE의 ORM·서비스 구조와 AI 구현이 서로 직접 의존하지 않게 한다.
- 누락된 값이나 예상하지 않은 필드를 경계에서 바로 검증한다.
- AI가 제안하고 BE가 저장·권한 확인·승인·실행한다는 책임을 분리한다.
- 양쪽이 합의된 요청·결과 형식을 기준으로 독립적으로 개발하고 테스트하게 한다.

세부 필드와 제약은 문서에 중복하지 않고 `contracts.py`를 기준으로 삼는다.

## 사용 흐름 예시

계획 대화 한 턴은 다음 순서로 처리한다.

```text
BE가 Event·Message 조회
  → EventConditions·ChatTurn으로 변환
  → PlanChatRequest로 AI 호출
  → AI가 PlanChatResult 반환
  → BE가 답변과 갱신된 행사 조건을 저장
```

아래 코드는 연동 형태를 보여주는 개념 예시다. 실제 함수명과 변환·저장 방식은
BE 연동 구현에서 확정한다.

```python
request = PlanChatRequest(
    event_id=event.id,
    conditions=to_event_conditions(event),
    messages=to_chat_turns(messages),
)

result = app.ai.plan_chat(request)

save_assistant_message(event.id, result.reply)
update_event_conditions(event, result.collected)
```

## 기록 색인 흐름 예시

파일 파싱이 끝난 기록 하나는 다음 순서로 색인한다.

```text
BE가 Record와 parse_result 조회
  → IndexRecordRequest로 변환 (record_id·file_name·file_type·blocks)
  → AI가 청킹·임베딩해 IndexRecordResult 반환 (청크: 텍스트·위치·임베딩)
  → BE가 청크에 기록 메타데이터를 붙여 저장하고 parseStatus를 INDEXED로 변경
```

AI는 청크 내용만 만든다. `club_id`·`event_id`·`category` 같은 기록 메타데이터는
AI에 넘기지 않고, BE가 저장할 때 청크에 붙인다.

```python
request = IndexRecordRequest(
    record_id=record.id,
    file_name=record.file_name,
    file_type=record.file_type,  # 파일 없는 텍스트 기록이면 None
    blocks=record.parse_result["blocks"],
)

try:
    result = await app.ai.index_record(request)
except app.ai.AIEmptyRecordError:
    mark_failed(record)  # 읽을 내용이 없다. 다시 시도해도 같다
    return
# AIRetryableError(임베딩 호출 실패)는 다시 시도할 수 있다. 처리 방식은 BE가 정한다

save_chunks(record, result.chunks)  # 메타데이터를 붙여 저장, INDEXED로 변경
```

`parse_result` 형식은 [예시 기록](../tests/fixtures/records/README.md)을 기준으로 한다.
블록마다 본문과 원문 위치(`location.label`)를 둔다. 청크 라벨은 이 위치에 조항·소제목이나 행 범위를 더한 것이며
(예: `2쪽` → `2쪽 · 제10조(참가비 환불)`), 답변의 출처로 그대로 쓰인다.

## 회의 발화 처리 초안

> 상태: AI 초안(2026-10-13 작성, 10-14 보강). #113에서 BE와 합의하기 전이다.
> BE가 연결해 볼 수 있도록 `app.ai.judge_utterance`와 아래 타입을 초안 그대로 공개했다(#72). 합의하면서 바뀔 수 있다.
> 합의 전에는 `contracts.py`에 옮기지 않고(타입은 `features/meeting/schemas.py`), 합의하면 코드로 옮긴 뒤 이 절은 사용 흐름 예시만 남긴다.

회의 중 발화 하나가 들어올 때마다 BE가 `app.ai.judge_utterance`를 부른다.
AI는 기록 조회가 필요한지 판단하고, 필요하면 기록을 찾아 출처가 붙은 답을 돌려준다(AI-MEET).

```text
BE가 VAD로 자른 구간을 Whisper로 텍스트로 만든다
  → 발화에 id와 순번을 붙여 회의 기록에 넣는다
  → 이번 발화와 바로 앞 발화들을 실어 judge_utterance를 부른다
    발화마다 따로 실행하고, 앞 발화의 처리를 기다리지 않는다
AI가 앞 발화와 함께 판단한다
  → 조회가 필요 없으면 NO_LOOKUP
  → 필요하면 검색어를 만들어 기록을 찾고, 무엇에 대한 답인지와 함께 답을 만든다
BE는 ANSWER·NOT_FOUND를 도착하는 대로 화면으로 보낸다. 늦게 와도 보낸다
```

### 입력과 결과

판단과 검색어 구성을 나누는 일은 AI 내부에서 한다(#114). BE는 발화마다 한 번 부르고 결과 하나를 받는다.

```python
class MeetingUtterance(ContractModel):
    utterance_id: str      # BE가 붙인다
    seq: int               # 회의 안에서 1부터 하나씩 커진다. 재연결해도 이어진다
    version: int = 1       # 전사 버전. 같은 발화의 전사가 고쳐지면 커진다
    text: str              # Whisper 확정 전사. 중간 전사는 넘기지 않는다. AI는 고치지 않는다
    started_at: datetime   # VAD 구간 시작. 회의 날짜("작년"을 연도로 풀 때)도 여기서 얻는다
    ended_at: datetime     # VAD 구간 끝. 지연 측정에 쓴다


class MeetingEvent(ContractModel):
    """회의가 특정 행사에 묶여 있을 때 그 행사. 검색어를 만들 때 참고한다"""

    event_id: str
    title: str                       # 예: "2026 봄 MT"
    event_type: EventType | None = None
    start_date: date | None = None


class JudgeUtteranceRequest(ContractModel):
    meeting_id: str
    club_id: str           # 이 회의가 볼 수 있는 기록 범위. BE가 권한을 확인한 값
    utterance: MeetingUtterance
    # 바로 앞 발화들. 순번 순서로 최대 MEETING_CONTEXT_UTTERANCES개
    context: tuple[MeetingUtterance, ...] = ()
    event: MeetingEvent | None = None   # 회의를 행사에 묶지 않았으면 None


class ToolCall(ContractModel):
    """판단 뒤 AI가 실제로 부른 도구 하나"""

    tool: Literal["records.search", "llm.generate"]
    input: str                       # 예: 검색어 "2025 봄 MT 숙소비"
    status: Literal["OK", "FAILED", "TIMEOUT"]
    duration_ms: int
    result_count: int | None = None  # records.search일 때 찾은 조각 수
    prompt_version: str | None = None  # llm.generate일 때 그 호출의 프롬프트 버전. 예: "records-assess-v1"


class JudgeTrace(ContractModel):
    """이 판단을 누가, 어떤 지시로 내렸고 무엇을 했는지. BE가 판단 기록으로 저장한다"""

    model: str                       # 예: "gpt-5.6-luna". Laya·Jev로 바꾸면 그 이름
    prompt_version: str              # 예: "meeting-judge-v5"
    judge_ms: int                    # 판단(과 검색어) 호출에 걸린 시간
    tool_calls: tuple[ToolCall, ...] = ()   # NONE이면 비어 있다


class JudgeUtteranceResult(ContractModel):
    utterance_id: str
    source_version: int    # 판단에 쓴 전사 버전. 요청의 utterance.version을 그대로 돌려준다
    # 어떤 처리로 갔는지. 지금은 RAG(기록 조회)와 NONE뿐이고 나중에 LLM이 추가된다
    route: Literal["RAG", "NONE"]
    kind: Literal["NO_LOOKUP", "ANSWER", "NOT_FOUND"]
    # 무엇에 대한 답인지. 검색어 구성 단계가 만든 검색어다. NO_LOOKUP이면 None
    question: str | None = None
    answer: str | None = None                # ANSWER일 때만
    sources: tuple[RecordSource, ...] = ()   # ANSWER일 때 하나 이상
    trace: JudgeTrace


# 처리 단계. 화면의 진행 표시(activity)에 쓴다
MeetingStage = Literal["JUDGING", "SEARCHING", "ANSWERING"]


class MeetingProgressPort(Protocol):
    """단계가 바뀔 때 AI가 알린다. 구현체는 BE가 주입한다"""

    async def stage_changed(self, utterance_id: str, stage: MeetingStage) -> None: ...


# 문맥으로 실어 보낼 앞 발화 수. AI가 정하고 BE는 이 값을 따른다
MEETING_CONTEXT_UTTERANCES: int


async def judge_utterance(
    request: JudgeUtteranceRequest,
    *,
    records: RecordSearchPort,
    progress: MeetingProgressPort | None = None,
) -> JudgeUtteranceResult: ...
```

화면에는 `question`과 원래 발화의 시각을 답과 함께 띄운다.
대화가 넘어간 뒤에 떠도, 질문을 고쳐 답이 두 개 떠도 어느 답이 어느 질문에 대한 것인지 구분된다(AI-MEET-06).
`question`은 검색어 구성 단계가 만든 검색어를 그대로 쓴다. 오인식 보정 사전으로 후보를 넓히기 전의 값이다.
앞 발화로 "그때" 같은 지시어를 풀어 만든 값이라, 따로 호출하지 않아도 Whisper 원문보다 무엇을 물었는지 잘 드러난다.
`question`은 판단이 아니라 검색어에 묶여 있다. 판단을 Laya 같은 판단 전용 모델로 바꿔도 검색어는 LLM이 만들어야 하므로([판단 모델](architecture.md#판단-모델)), 그 단계가 만든 검색어를 그대로 쓰면 된다. 지금은 판단과 검색어를 한 호출에서 받는다.
검색어에 오인식이 남거나 화면에 띄우기 어색하면, 검색어 출력에 필드를 더하지 않고 답을 만들 때 다시 쓴다. 출력 필드가 늘면 지연이 바로 늘기 때문이다([측정 기록](meeting-evaluation.md)).

```text
┌ 2025 회비 금액 · 12초 전
│ 2025 학기 회비 20,000원 (2025 회비 수납 장부 · 2~15행)
└ [닫기]
```

### 답 문구 — 기록 검색 결과를 옮긴다

답은 기록 검색 `search_records`(#72)와 같은 단계로 만든다. 판단이 만든 검색어로 청크를 찾고(`find_chunks`), 찾은 청크로 근거를 판단한다(`assess_chunks`).
검색어는 판단이 이미 정리했으므로 다시 정리하지 않고, 다시 찾지도 않는다. 기준일은 회의 날짜다.
근거 판단 결과(확인한 사실, 확인하지 못한 것, 자료 간 차이)를 코드가 카드 문구로 옮긴다. 모델을 다시 부르지 않는다.

| 근거 판단 결과 | `kind` · `answer` |
| --- | --- |
| 확인한 사실 | `ANSWER` · 사실 문구를 한 줄에 하나씩. 예: "2025 봄 MT 숙박비 550,000원" |
| 자료 간 차이 | `ANSWER` · 하나를 고르지 않고 값마다 문서 이름을 붙인다(AI-RET-03). 예: "2025 봄 MT 참가 인원: 28명 (2025 봄 MT 결과보고.pdf) / 27명 (2025 상반기 장부.xlsx)" |
| 사실과 확인하지 못한 것이 함께 | `ANSWER` · 사실 뒤에 한 줄을 덧붙인다. 예: "기록에 없음: 숙소비 세부 내역" |
| 확인하지 못한 것만 | `NOT_FOUND` |
| 찾은 청크가 없음 | `NOT_FOUND`. 근거 판단을 부르지 않는다 |

- 사실 문구에는 어느 기록의 값인지 알 수 있게 연도와 행사 이름이 들어간다. 근거 판단 규칙이다.
- `sources`는 사실과 자료 간 차이에 쓰인 출처를 나온 순서대로 한 번씩 담는다. 모두 검색된 청크에서 옮긴 것이다(AI-RET-02).
- 출처에는 문서 이름과 위치만 있고 청크 원문은 없다. 카드에 원문 조각까지 보여줄지는 화면과 함께 정한다.

| 발화 (앞 발화) | 결과 | 화면 |
| --- | --- | --- |
| "작년 MT 때 숙소비 얼마 나왔지?" | `ANSWER` · "2025 봄 MT 숙박비 550,000원" · 출처 `2025 봄 MT 결과보고 · 2쪽 · 2. 예산` | 질문과 답, 출처 |
| "그때 인원은?" (앞: "작년 봄 MT 얘기인데") | `ANSWER` · question "2025 봄 MT 참가 인원" | 질문과 답, 출처 |
| "민수야 예약했어?" | `NO_LOOKUP` | 띄우지 않음 |
| "재작년 신환회 장소 어디였지?" (관련 기록 없음) | `NOT_FOUND` · question "2024 신환회 장소" | 기록에 없음 |
| "작년 회비 얼마였지?" 뒤 검색 중에 "점심 뭐 먹지" | `ANSWER` | 늦게 와도 질문과 함께 띄움 |
| 모델 호출 시간 초과 | `AITimeoutError` (`trace` 포함) | 처리하지 못함 |

### 판단 기록 — `route`, `source_version`, `trace`

BE는 발화마다 판단 기록을 저장한다(PM 서비스 계약 제안(10-12)의 `context-decisions`, #117). AI는 DB에 쓰지 않으므로 저장할 값을 결과에 담아 돌려준다.

```json
{
  "utterance_id": "u-31",
  "source_version": 1,
  "route": "RAG",
  "kind": "ANSWER",
  "question": "2025 봄 MT 숙소비",
  "answer": "2025 봄 MT 숙박비 550,000원",
  "sources": [{"record_id": "r-12", "file_name": "2025 봄 MT 결과보고", "location": {"label": "2쪽 · 2. 예산"}}],
  "trace": {
    "model": "gpt-5.6-luna",
    "prompt_version": "meeting-judge-v5",
    "judge_ms": 1480,
    "tool_calls": [
      {"tool": "records.search", "input": "2025 봄 MT 숙소비", "status": "OK", "duration_ms": 480, "result_count": 5},
      {"tool": "llm.generate", "input": "2025 봄 MT 숙소비", "status": "OK", "duration_ms": 3490, "prompt_version": "records-assess-v1"}
    ]
  }
}
```

| 값 | 쓰임 | 예 |
| --- | --- | --- |
| `source_version` | 전사가 나중에 고쳐지면, 옛 버전으로 내린 판단을 BE가 가려낸다(STALE) | 1번 버전 "회측"으로 판단 → 2번 버전 "회칙"으로 고쳐짐 → 1번 판단은 지난 것 |
| `route` | 무슨 종류의 처리였는지 화면과 통계에서 본다 | "이번 회의에서 RAG 7번, NONE 120번" |
| `trace.tool_calls` | 답이 틀리거나 늦을 때 어느 단계가 원인인지 찾는다 | 6초 걸림 → 검색 0.4초, 답 작성 5.5초 |
| `trace.model`, `prompt_version` | 모델·프롬프트를 바꾼 전후를 나눠 비교하고, 학습 데이터를 고른다(#117) | v3a와 v4의 오탐률 비교 |
| `tool_calls[].prompt_version` | 답을 쓴 근거 판단 지시문이 바뀐 전후를 나눠 본다 | `records-assess-v1`과 v2의 "기록에 없음" 비율 비교 |

- **이 값들은 모델이 만들지 않고 AI 코드가 채운다.** 버전은 받은 값을 돌려주고, 시간은 코드가 재고, 모델·프롬프트 버전은 설정값이다. 모델 출력이 늘지 않으므로 판단 지연은 그대로다.
- **조회하지 않은 이유(`reasonCode`)는 실시간 결과에 넣지 않는다.** 이유를 모델이 출력하게 하면 판단이 느려진다. 이유 문장과 확신도를 빼서 p50이 0.65초 줄었다(#111). 이유는 검수용이므로 회의가 끝난 뒤 별도 호출로 채운다(#114, #117).
  값은 아래 일곱 중 하나이고 `route`가 `NONE`일 때만 채운다. `RAG`면 검색어가 곧 이유라 비운다. 기준은 `features/meeting/schemas.py`의 `ReasonCode`다.

  | 값 | 뜻 | 예 |
  | --- | --- | --- |
  | `CURRENT_STATUS` | 기록에 없는 지금 일을 묻는 말 | "민수야 예약했어?" |
  | `MONOLOGUE` | 혼잣말·감탄 | "이게 맞나" |
  | `CHITCHAT` | 기록과 무관한 잡담·부탁 | "점심 뭐 먹지?", "화면 좀 넘겨 줄래?" |
  | `FUTURE_DECISION` | 앞으로 할 일을 정하는 말 | "이번엔 버스 대절하죠" |
  | `REFERENCE_MATERIAL` | 과거 자료를 같이 보자는 말. 이 코드가 붙은 발화 수로 자료 열기 안내(`record_reference`)를 만들지 정한다 | "작년 축제 자료 펴 놓고 얘기해요" |
  | `NEEDS_CONTEXT` | 가리키는 대상을 아직 알 수 없는 말 | 앞에 대상이 없는 "그거 얼마였지?" |
  | `OTHER` | 어디에도 맞지 않음. 자주 나오는 유형은 값으로 늘린다 | |

  앞의 다섯은 판단 프롬프트의 "조회가 필요 없는 경우"와 하나씩 맞춘다. 모델이 보는 기준과 사람이 검수하는 기준을 같게 하기 위해서다. 사람을 불렀는지는 기준이 아니다. "민수야, 작년 회칙상 환불 기준이 뭐였지?"는 `RAG`다(AI-MEET-01).
- **`route`에는 나중에 `LLM`이 추가된다.** 회의 중 AI에게 직접 시키는 기능이다. BE는 모르는 `route` 값이 와도 깨지지 않게 처리한다.

### 처리 단계 — `progress`

화면의 진행 표시에 지금 어느 단계인지 보여줄 수 있도록, AI는 단계가 바뀔 때 `progress.stage_changed`를 부른다. 넘기지 않으면 알리지 않는다.

```text
발화 u-31  JUDGING   판단과 검색어 구성
           SEARCHING 기록 검색          ← 조회가 필요할 때만
           ANSWERING 답 작성            ← 근거를 찾았을 때만
           (결과 반환)
```

조회가 필요 없는 발화(대부분)는 JUDGING만 거친다. 화면에서 단계까지 보여줄지는 FE와 정한다.

### 행사 정보 — `event`

회의를 행사에 묶어 만들었다면 그 행사를 넘긴다. "이번 거", "그 행사"를 풀 때 쓴다.

```text
회의: 2026 봄 MT 준비 (event 있음)
발화: "이번 거 참가비 상한이 회칙에 있었나?"
  event 없음 → "참가비 상한"
  event 있음 → "MT 참가비 상한"
```

검색 범위를 그 행사로 좁히지는 않는다. 검색 범위는 `club_id`다.

### 함께 정할 네 가지 — AI 안

| 항목 | AI 안 | 이유 |
| --- | --- | --- |
| 회의 상태와 최근 문맥의 주인 | **BE.** 회의 기록은 BE가 들고, 부를 때마다 앞 발화를 `context`로 실어 보낸다. 몇 개를 보낼지는 AI가 `MEETING_CONTEXT_UTTERANCES`로 공개한다. AI는 호출 사이에 아무것도 들고 있지 않는다 | 회의 세션이 BE 프로세스 안에 있고 발화 텍스트도 BE가 남긴다(#117). 둘이 따로 들면 어긋난다. AI가 상태를 들지 않으므로 재연결·재시작 때 AI 쪽에서 잃는 것이 없고, 회의 시작·종료 함수도 필요 없다. 실제로 넘긴 문맥이 요청에 남아 그대로 로그로 쓸 수 있다 |
| 발화 식별자와 순번 | **BE가 붙인다.** `seq`는 회의마다 1부터 하나씩 커지고 WebSocket을 다시 연결해도 이어진다. 결과는 `utterance_id`로 어느 발화의 답인지 맞춘다 | 결과가 발화 순서대로 오지 않는다. 문장별 시각이 없으므로(#111) VAD 구간의 시작·끝을 발화 시각으로 쓴다. 구간 하나가 발화 하나다 |
| 늦은 결과 | **버리지 않는다.** 늦게 와도 `question`과 원래 발화 시각을 붙여 띄운다. 제한 시간을 넘기면 조용히 버리지 않고 처리하지 못했다고 알린다 | 답이 느리면 기다리며 다른 이야기를 하는 것이 자연스럽다. 필요 없는 답은 닫으면 되지만(AI-MEET-05), 물어본 답이 뜨지 않으면 고장인지 알 수 없다(AI-MEET-06) |
| 검색 권한 범위 | **요청의 `club_id`.** BE가 회의 세션을 만들 때 권한을 확인한 동아리다. AI는 이 값을 `ChunkSearchQuery.club_id`에 그대로 넣고 넓히지 않는다 | 기록 검색과 같은 방식이다. 범위 제한은 `RecordSearchPort` 구현(BE)이 한다 |

### 비동기와 실패

- 발화마다 따로 실행한다. 앞 발화의 검색이 길어져도 다음 발화의 판단을 막지 않는다(AI-MEET-06).
- `judge_utterance`는 BE 상태를 바꾸지 않는다. 회의가 끝나면 BE가 진행 중인 호출을 취소해도 된다.
- 제한 시간은 AI가 호출 안에서 지키고, 넘기면 `AITimeoutError`를 올린다.
- 처리에 실패하면 빈 결과가 아니라 [AI 오류 타입](errors.md)을 올린다. BE는 `AIError`를 "처리하지 못함"으로 보여주고 **자동으로 다시 시도하지 않는다.** 회의 듣기는 계속한다(AI-MEET-07).
- **실패한 판단도 판단 기록에 남긴다(#117).** 올리는 오류의 `trace`에 실패하기 전까지의 판단 기록(`JudgeTrace`)이 들어 있다. BE는 이 값을 `status=FAILED`인 판단 기록으로 저장한다. 실패한 판단을 빼고 모으면 어떤 발화에서 얼마나 자주 실패하는지 셀 수 없다.

  ```python
  try:
      result = await app.ai.judge_utterance(request, records=records)
  except app.ai.AIError as error:
      save_failed_decision(request.utterance, error.trace)  # 오류 종류와 함께 저장
      show_not_processed(request.utterance)
  ```

  | 실패한 곳 | 오류 | `trace` |
  | --- | --- | --- |
  | 판단 시간 초과 | `AITimeoutError` | `judge_ms` 약 10000, `tool_calls` 없음 |
  | 판단 응답이 형식에 맞지 않음 | `AIInvalidResponseError` | `tool_calls` 없음 |
  | 기록 검색 | 검색이 올린 오류 | `records.search`가 `FAILED` 또는 `TIMEOUT` |
  | 답 작성 | 답 작성이 올린 오류 | `records.search`는 `OK`, `llm.generate`가 `FAILED` 또는 `TIMEOUT` |

  예상하지 못한 예외(`AIError`가 아닌 것)는 `trace` 없이 그대로 올라간다. BE는 서버 오류로 처리한다.
- 운영진이 직접 다시 판단을 요청하면 같은 요청으로 다시 부를 수 있다. 회의를 멈추지 않으므로 자동 재시도와 다르다. 이전 실패 기록은 BE가 남긴다.
- 음성 인식 실패는 BE에서 끝난다. AI를 부르지 않고 BE가 "처리하지 못함"으로 보여준다.
- 관련 기록이 없는 것은 실패가 아니라 `NOT_FOUND`다.

### 지원 범위

- **한국어 회의만 다룬다.** 판단 프롬프트와 측정을 한국어로만 했다.
- **누가 말했는지는 쓰지 않는다.** 화자분리는 범위 밖이다([아키텍처](architecture.md#다루지-않는-것)). 전사에 화자 표시 칸이 있어도 AI에는 넘기지 않는다.

### 아직 정하지 않은 것

- port 주입 방식. 초안은 키워드 인자로 받는다. BE의 AI 초기화 방식과 맞춘다.
- 판단 기록의 저장 형식과 보관 기간(#117). 결과와 오류에 담을 값은 위 "판단 기록"과 "비동기와 실패"로 정했다.
- 처리 단계를 화면에 보여줄지(FE), `progress`를 넘기는 방식.
- 제한 시간 값. 기록 검색은 근거 판단의 추론 깊이 기본값으로 p50 4.03초, p95 7.74초였다([기록 색인·검색 평가 기록](retrieval-evaluation.md)). 회의에서 추론을 끌지 잰 뒤 정한다.
- 카드에 근거 원문 조각을 보여줄지(FE·PM). 보여준다면 결과의 출처에 청크 원문을 더한다.
