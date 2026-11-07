# BE-AI 데이터 계약 (contracts.py)

새 P1의 공개 입출력은 [P1 공개 계약](planning/p1-public-contract.md)을 따른다. 화면용 결과와 BE 보관 상태를 구분하며, #180/#181에서 타입과 실행 함수를 구현했다. #235/#236에서 제품 BE의 실제 검색·상세 응답·마지막 조회 복원을 연결했다. 제품 출처 카드의 FE 연결은 후속이다.

새 P1 Agent의 제품 연결은 [P1 인계 안내](planning/p1-handoff.md)와 [협업 이슈 #179](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/179)에서 계약을 맞춘다. 실행 사용처가 없던 이전 계획 대화 요청/응답은 제거했다(#182). 현재는 `PlanningChatRequest`와 `PlanningPublicResult`를 사용한다.

## 무엇인가

[`contracts.py`](../contracts.py)는 BE와 AI 모듈이 같은 프로세스 안에서 주고받는
요청·결과의 형식을 정의한다. DB 모델이나 FE 공개 API 스키마가 아니라,
`app.ai` 경계를 위한 내부 계약이다.

행사 계획(조건 수집·계획안 생성)과 기록 색인에 필요한 타입을 정의한다.
기록 색인은 `app.ai.index_record`, P1은 `app.ai.chat_planning`과 `app.ai.generate_planning_preview`로 호출한다. P1 검색 port와 제품 응답·복원 필드는 [인계 안내 §9](planning/p1-handoff.md#9-검색-기능을-연결하려면)를 따른다.
회의 발화 처리는 #113에서 합의할 AI 초안을 [아래](#회의-발화-처리-초안)에 둔다.

## 왜 필요한가

- BE의 ORM·서비스 구조와 AI 구현이 서로 직접 의존하지 않게 한다.
- 누락된 값이나 예상하지 않은 필드를 경계에서 바로 검증한다.
- AI가 제안하고 BE가 저장·권한 확인·승인·실행한다는 책임을 분리한다.
- 양쪽이 합의된 요청·결과 형식을 기준으로 독립적으로 개발하고 테스트하게 한다.

P1 공개 요청과 결과, 그 안에 담기는 조건/초안/검색 결과는 루트 `contracts.py`에 정의한다. 공개 오류는 `errors.py`, 실행 함수는 `facade.py`를 기준으로 한다. `planning_contracts.py`는 이전 import 경로의 호환용이며 별도 타입 정의가 없다. BE는 `app.ai`에서 가져온다.

## 사용 흐름 예시

```text
BE가 현재 행사 조건과 저장된 Agent 상태 조회
  → PlanningChatRequest로 이번 사용자 메시지 전달
  → await app.ai.chat_planning(request, records=record_search_port)
  → PlanningPublicResult 반환
  → BE가 revision 확인 후 조건, 답변, next_state를 함께 저장
  → FE에 view를 제품 응답으로 변환해 전달
```

실행 가능한 요청 구성과 버튼 생성 예시는 [P1 공개 계약 11절](planning/p1-public-contract.md#11-3번-작업-공개-함수로-실행하기-181)을 따른다. AI 함수가 DB 저장이나 상태 버전 증가를 대신하지 않는다.

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
    """발화 하나를 처리하며 AI가 실제로 부른 도구 하나"""

    # judge.decide: 판단(Jev), records.search: 기록 검색, llm.generate: 검색어 만들기·답 작성
    tool: Literal["judge.decide", "records.search", "llm.generate"]
    input: str                       # 판단·검색어 만들기는 방금 발화, 검색·답 작성은 검색어 "2025 봄 MT 숙소비"
    status: Literal["OK", "FAILED", "TIMEOUT"]
    duration_ms: int
    result_count: int | None = None  # records.search일 때 찾은 조각 수
    prompt_version: str | None = None  # llm.generate일 때 그 호출의 프롬프트 버전. 예: "meeting-query-v1", "records-assess-v1+meeting-assess-v2"
    probability: float | None = None   # judge.decide일 때 Jev가 낸 조회가 필요할 확률(0~1)


class JudgeTrace(ContractModel):
    """이 판단을 누가, 어떤 지시로 내렸고 무엇을 했는지. BE가 판단 기록으로 저장한다"""

    model: str                       # 판단 모델. "typesafe/jev-1.14" (코드에 고정)
    prompt_version: str              # 판단 질문 문구의 버전. "meeting-questions-v1"
    judge_ms: int                    # 판단 단계에 걸린 시간. 조회로 본 발화는 검색어 만들기까지 들어간다
    tool_calls: tuple[ToolCall, ...] = ()   # 부른 순서대로. 판단(judge.decide)이 늘 처음이고, NONE이면 그것 하나다


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
`question`은 검색어 구성 단계가 만든 검색어를 그대로 쓴다.
앞 발화로 "그때" 같은 지시어를 풀어 만든 값이라, 따로 호출하지 않아도 Whisper 원문보다 무엇을 물었는지 잘 드러난다.
`question`은 판단이 아니라 검색어에 묶여 있다. 판단은 판단 전용 모델 Jev가 하고 검색어는 Jev가 조회로 본 발화에만 LLM(luna)이 만들므로([판단 모델](architecture.md#판단-모델)), 그 단계가 만든 검색어를 그대로 쓰면 된다.
검색어에 오인식이 남거나 화면에 띄우기 어색하면, 검색어 출력에 필드를 더하지 않고 답을 만들 때 다시 쓴다. 출력 필드가 늘면 지연이 바로 늘기 때문이다([측정 기록](meeting-evaluation.md)).

```text
┌ 2025 회비 금액 · 12초 전
│ 2025 학기 회비 20,000원 (2025 회비 수납 장부 · 2~15행)
└ [닫기]
```

### 답 문구 — 기록 검색 결과를 옮긴다

답은 기록 검색 `search_records`(#72)와 같은 단계로 만든다. 판단이 만든 검색어로 청크를 찾고(`find_chunks`), 찾은 청크로 근거를 판단한다(`assess_chunks`).
검색어는 판단이 이미 정리했으므로 다시 정리하지 않고, 다시 찾지도 않는다. 기준일은 회의 날짜다.
회의 답의 금액·인원 등 숫자와 연도는 토리 자료 답변과 같은 방식으로 인용 청크의 원문과 문서명 연도를 확인한다. 근거가 없는 숫자는 제외하고 미확인으로 표시한다. 숫자는 값으로 읽어 비교하므로 `45000`과 `45,000원`, `10만원`과 `100,000원`은 같은 숫자로 본다(#383). 이 검사는 숫자가 원문에 있는지만 확인하므로 의미적 정확성을 보장하지 않으며, 계산한 값은 제외된다.

회의 원발화는 검색어와 별도로 근거 판단에 전달한다. 검색어 재작성에서 회고·최근 표현이 빠져도 원발화를 함께 확인한다. 회고 또는 최근 행사 참가 인원 질문은 한 번의 벡터 검색에서 후보 20개를 받아 원래 상위 3개를 보존하고 질문한 항목의 본문 최대 2개를 보충해 모델에는 5개만 보낸다. 명시 연도가 있으면 보충 자료도 그 연도와 일치해야 한다. 그 밖의 질문은 기존 상위 5개다. 검색된 자료만으로 전체 최신을 확정할 수 없어 최근 질문의 답에는 그 한계를 표시한다. 현재 진행 중인 행사의 실제 상태는 기록 검색으로 확정하지 않는다.
근거 판단 결과(확인한 사실, 확인하지 못한 것, 자료 간 차이)를 코드가 카드 문구로 옮긴다. 모델을 다시 부르지 않는다.

| 근거 판단 결과 | `kind` · `answer` |
| --- | --- |
| 확인한 사실 | `ANSWER` · 사실 문구를 한 줄에 하나씩. 예: "2025 봄 MT 숙박비 550,000원" |
| 자료 간 차이 | `ANSWER` · 하나를 고르지 않고 값마다 문서 이름을 붙인다(AI-RET-03). 예: "2025 봄 MT 참가 인원: 28명 (2025 봄 MT 결과보고.pdf) / 27명 (2025 상반기 장부.xlsx)" |
| 사실과 확인하지 못한 것이 함께 | `ANSWER` · 사실 뒤에 한 줄을 덧붙인다. 예: "검색한 자료에서 확인하지 못함: 숙소비 세부 내역" |
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
| "재작년 신환회 장소 어디였지?" (관련 기록 없음) | `NOT_FOUND` · question "2024 신환회 장소" | 검색한 자료에서 확인하지 못함 |
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
    "model": "typesafe/jev-1.14",
    "prompt_version": "meeting-questions-v1",
    "judge_ms": 2610,
    "tool_calls": [
      {"tool": "judge.decide", "input": "그때 숙소비 얼마였지?", "status": "OK", "duration_ms": 520, "probability": 0.83},
      {"tool": "llm.generate", "input": "그때 숙소비 얼마였지?", "status": "OK", "duration_ms": 2090, "prompt_version": "meeting-query-v1"},
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
| `trace.tool_calls` | 답이 틀리거나 늦을 때 어느 단계가 원인인지 찾는다 | 6초 걸림 → 판단 0.5초, 검색어 2.1초, 검색 0.4초, 답 작성 3.0초 |
| `tool_calls[].probability` | 임계값(0.35)을 바꾸면 판단이 어떻게 달라지는지 회의 뒤에 다시 센다. 0.35 근처에서 떴다 안 떴다 한 말을 찾는다 | "0.30으로 내리면 이 회의에서 카드가 3장 더 뜬다" |
| `trace.model`, `prompt_version` | 모델·질문 문구를 바꾼 전후를 나눠 비교하고, 학습 데이터를 고른다(#117) | `meeting-questions-v1`과 v2의 놓침 비교 |
| `tool_calls[].prompt_version` | 답을 쓴 근거 판단 지시문이 바뀐 전후를 나눠 본다 | `records-assess-v1`과 v2의 "기록에 없음" 비율 비교 |

- **BE는 판단에 넘긴 요청도 함께 저장한다(#241).** 판단 기록의 `judge_input`에 `JudgeUtteranceRequest`를 그대로(시각은 ISO 문자열로) 남기고, `trace.judge_ms`를 `judge_ms`에 남긴다. 전사는 고치면 덮어써지므로 발화 id와 version으로는 그때 모델이 본 앞 발화를 다시 만들 수 없다. 실패한 판단은 오류의 `trace`에서 `judge_ms`를 꺼내고, `trace`가 없으면 비운다.
- **이 값들은 모델이 만들지 않고 AI 코드가 채운다.** 버전은 받은 값을 돌려주고, 시간은 코드가 재고, 모델·질문 문구 버전은 코드에 고정한 값이다. 확률은 Jev 응답을 그대로 옮긴다.
- **BE는 `tool_calls`를 JSON 그대로 저장하므로 확률을 담으려고 DB를 바꾸지 않는다(#255).** 판단 모델은 `model_version`에, 질문 문구 버전은 `policy_version`에 들어간다.
- **조회하지 않은 이유(`reasonCode`)는 실시간 결과에 넣지 않는다.** 판단 모델은 확률만 내고, luna로 판단할 때도 이유를 출력하게 하면 판단이 느려졌다. 이유 문장과 확신도를 빼서 p50이 0.65초 줄었다(#111). 이유는 검수용이므로 회의가 끝난 뒤 별도 호출로 채운다(#114, #117).
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
발화 u-31  JUDGING   판단(Jev)과 검색어 구성(조회일 때 luna)
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
  event 없음 → "이번 행사 참가비 상한"
  event 있음 → "2026 봄 MT 참가비 상한"
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
  | 판단 단계 시간 초과 (Jev와 검색어 호출을 합쳐 10초) | `AITimeoutError` | `judge_ms` 약 10000. 끝난 호출만 남는다 |
  | Jev 호출 | 연결·429·5xx는 `AIRetryableError`, 키·주소는 `AIConfigError`, 확률이 없으면 `AIInvalidResponseError` | `judge.decide`가 `FAILED` 또는 `TIMEOUT` |
  | 검색어 호출 | 모델 호출 오류. 검색어가 비면 `AIInvalidResponseError` | `judge.decide`는 `OK`, `llm.generate`(`meeting-query-v1`)가 `FAILED` 또는 `TIMEOUT` |
  | 기록 검색 | 검색이 올린 오류 | 앞의 두 줄 다음 `records.search`가 `FAILED` 또는 `TIMEOUT` |
  | 답 작성 | 답 작성이 올린 오류 | `records.search`는 `OK`, 마지막 `llm.generate`가 `FAILED` 또는 `TIMEOUT` |

  Jev가 실패해도 luna로 대신 판단하지 않는다. 두 모델이 같은 게이트웨이를 거쳐 함께 멈추기 때문이다([판단 모델](architecture.md#판단-모델)).

  예상하지 못한 예외(`AIError`가 아닌 것)는 `trace` 없이 그대로 올라간다. BE는 서버 오류로 처리한다.
- 운영진이 직접 다시 판단을 요청하면 같은 요청으로 다시 부를 수 있다. 회의를 멈추지 않으므로 자동 재시도와 다르다. 이전 실패 기록은 BE가 남긴다.
- 음성 인식 실패는 BE에서 끝난다. AI를 부르지 않고 BE가 "처리하지 못함"으로 보여준다.
- 관련 기록이 없는 것은 실패가 아니라 `NOT_FOUND`다.

### 지원 범위

- **한국어 회의만 다룬다.** 판단 프롬프트와 측정을 한국어로만 했다.
- **누가 말했는지는 쓰지 않는다.** 화자분리는 범위 밖이다([아키텍처](architecture.md#다루지-않는-것)). 전사에 화자 표시 칸이 있어도 AI에는 넘기지 않는다.

### 아직 정하지 않은 것

- port 주입 방식. 초안은 키워드 인자로 받는다. BE의 AI 초기화 방식과 맞춘다.
- 판단 기록의 보관 기간(#117). 저장하는 값은 위 "판단 기록"과 "비동기와 실패"로 정했다. `judge_input`에 전사 원문이 복사되므로 회의·전사를 지울 때 함께 지울지도 같이 정한다.
- 처리 단계를 화면에 보여줄지(FE), `progress`를 넘기는 방식.
- 제한 시간 값. 회의 설정(근거 판단 추론 끔)의 기록 검색은 p50 2.52초, p95 3.78초였다([측정 기록](meeting-evaluation.md)). 판단부터 답까지 한 번에 잰 뒤 정한다.
- 답 카드의 길이. 사실이 여러 개면 한 줄씩 늘어나 4줄 이상인 답이 약 39개 중 7~9개였다. 화면에서 접어 보여줄지(FE)와 함께 정한다.
- 카드에 근거 원문 조각을 보여줄지(FE·PM). 보여준다면 결과의 출처에 청크 원문을 더한다.

## 계획 수정 후 검토 (#177)

BE는 생성 직후 계획과 현재 계획을 비교해 `PlanEditReviewRequest`를 만들고 `await app.ai.review_plan_edit(request)`를 호출한다. AI는 저장·확정을 하지 않고 걱정되는 점만 돌려준다.

입력 `PlanEditReviewRequest`: `draft`(P1 `PlanningDraft`, 잠정 여부와 미룬 주제 포함), `today`, `included_steps`(순서대로, 단계 코드·이름·phase·actor·일정·행동), `excluded_steps`(`excluded_by`가 `ai`면 처음 생성 때 AI가 뺀 것, `user`면 사용자가 뺀 것), `changes`(`removed_codes`, `added_codes`, `moved_codes`, `schedule_changes`, `action_changes`). 모두 BE가 채우며 AI는 이 입력만 근거로 쓴다.

결과 `PlanEditReviewResult`: `outcome`(`issues`/`no_issues`)과 `items`(0~4개). 항목은 `step_codes`(1개 이상), `kind`(`missing_step`/`order`/`schedule`/`other`), `message`(해요체 1~2문장), `suggestion`(없으면 null)이다. `issues`는 항목 1개 이상, `no_issues`는 0개여야 계약 검증을 통과한다. 항목의 단계 코드가 입력의 포함·제외 단계에 없으면 `AIInvalidResponseError`로 막는다. 모델 실패는 다른 AI 호출처럼 `AIRetryableError` 등으로 전달되며 BE가 실패 상태로 저장한다.

```python
result = await app.ai.review_plan_edit(request)
# PlanEditReviewResult(outcome="issues", items=(PlanReviewItem(step_codes=("BOOK_VENUE","CONFIRM_DETAILS"), kind="order", ...),))
```

[코드 따라가기](planning/walkthrough.md#수정--검토-p2-계획-수정-후-ai-검토-177)와 [실제 모델 평가](planning/evaluation.md#계획-수정-검토-실제-모델-확인-177-ai-plan-07-2026-11-01)를 함께 본다.

## 회의 일정·할 일 후보 추출 초안

BE는 기존 회의 payload에 IANA `timezone`과 offset이 있는 `occurred_at`을 더해 `TaskExtractionRequest`를 만들고 `await app.ai.extract_task_suggestions(request)`를 호출한다. 최근 문맥은 지시 대상 해석에만 사용하며 현재 발화에서 새로 명시된 항목을 추출한다. 검색 판단과 독립 호출하므로 NONE이나 조회 실패에도 추출할 수 있다.

결과 `suggestions`는 `TaskSuggestion` 모델 목록이다. 각 모델은 `kind`(TASK/SCHEDULE), `title`, `description`, `suggested_assignee`, `due_date`, `due_at`, `scheduled_at`, `unresolved_fields`만 갖는다. 시각은 offset을 포함하고 불명확한 값은 null과 확인 필드로 남긴다. 모델이 빠뜨려도 TASK의 `due_at`, SCHEDULE의 `scheduled_at`, 미정 `suggested_assignee`는 확인 필드에 추가한다. 담당 이름은 계정이나 알림 수신자가 아니다. 빈 목록은 추출할 항목이 없다는 성공이고 모델 실패는 AI 오류로 전달한다. 후보를 확인·저장·예약하는 것은 BE와 운영진의 책임이다.


## 자료함의 관련 자료 검색

BE는 권한 확인 후 `app.ai.search_related_records(RecordDiscoveryRequest(club_id=..., query=..., limit=...), records=port)`를 호출한다. 기존 임베딩과 청크 검색을 사용해 `RetrievedChunk` 목록을 반환하며 각 청크에는 원문 텍스트, 문서 ID·이름·위치, 분류, 유사도가 있다. 유사도는 추천 순위이지 정답 확률이나 적합성 보장이 아니다. 검색 결과가 없으면 빈 튜플, 임베딩 실패는 AI 오류가 전파된다. 검색 port의 DB 오류도 숨기지 않는다. 색인 중/실패 등 상태, 권한, 파일명·본문 검색과 문서별 병합은 BE가 담당한다.


## 메인 토리 대화 의도

`classify_tori_intent(ToriIntentRequest(message, reference_date, timezone))`는 `record_search`, `task_list`, `event_planning`, `meeting`, `clarify`, `unsupported` 중 하나와 선택 필드를 반환한다. 검색어는 발화에 근거하며, 일정·할 일은 범위(self/all), 유형(task/schedule/all), 명시적으로 해석 가능한 날짜 범위만 반환한다. 현재 계약에는 회의·행사 식별이나 특정인 지정이 없으므로 해당 대상을 한정한 일정·할 일 요청은 일반 조회로 바꾸지 않고 unsupported 또는 clarify로 분류한다. 날짜만 정한 조회는 계속 허용한다. 모델이 자료 검색 외의 의도에 불필요한 query를 함께 반환하면 모델 출력 경계에서만 해당 query를 비운 뒤 엄격한 공개 계약으로 재검증한다. 자료 검색의 query 필수 및 다른 필드의 검증은 유지한다. 이 결과는 추정 분류이지 권한·실행 지시가 아니다. BE는 인증된 소속과 계정으로 실제 조회하고 변경·예약을 실행하지 않는다. 모델 오류는 AI 오류로 전파하며 실제 근거 없이 답을 만들지 않는다.


## 토리의 자료 질문 근거 판단

`answer_tori_records(ToriRecordAnswerRequest(question, today, chunks))`는 BE가 소속 권한을 확인해 제공한 검색 청크만 판단해 `status`(answered/partial/no_evidence), `facts`(사실과 출처), `conflicts`, `not_found`를 반환한다. 빈 청크는 no_evidence이며 모델 오류는 전파한다. 모델이 지정한 청크 ID를 출처 변환 전까지 유지하고, 그 청크의 숫자나 요청 연도의 직접 근거가 없는 사실은 제외해 미확인으로 표시한다. 같은 위치를 공유하는 다른 청크는 근거를 섞지 않는다. 숫자 비교는 숫자를 값과 단위로 나눠 한다(#383).
값은 쉼표·소수 끝 0을 정리하고 한글 큰 단위를 읽어 비교한다(`45,000.00`→45000, `4만 5천`→45000, `1억 2천만`→120000000, `십만`→100000). 큰 단위 순서가 어긋난 표기(`5천 4만`)는 원래 글자로 비교한다. 부호는 보존하고 명시적 양수 부호는 지운다.
단위는 원·명·개·건·%·년·월·일이며, `원`·`₩`·`\`는 숫자 앞뒤 어디에 있어도 원이다. 단위가 원문과 답변 양쪽에 있을 때만 같아야 하고, 한쪽에 없으면 값만 비교한다. 예: 원문 `금액: 45000`과 답변 `45,000원`은 통과, `45,000원`과 `45,000명`은 제외.
통화는 원만 지원한다. `$`·`달러`·`엔` 같은 외화 표시는 값을 읽지 않고 원 금액과 같은 값으로 통과하지 않게만 구분하며, 외화끼리는 구분하지 않는다.
괄호 금액은 양·음이 모호해 근거에서 제외한다. 고유어 수사(`한 명`, `스무 명`)는 원문과 같은 표기만 인정하고, 한자어 수사(`이십 명`)는 값으로 읽는다.
합산·나눗셈·비율처럼 계산한 값은 정당한 사실이어도 제외된다. 숫자 검사는 숫자가 어느 항목의 값인지 보지 않으므로 사실 전체의 정확성을 보장하지 않는다. 예: 원문 `참가 인원: 40, 회비: 20000`에서 `회비는 40원`도 통과한다. 자료 범위·미색인·검색 실패 및 권한은 BE가 안내한다. 회의·계획의 기존 검색 경로는 바꾸지 않는다.


### 토리 범위 질문과 후속 검색

`ToriRecordAnswerRequest`의 `question`은 원질문, `follow_up`은 선택적 후속 답, `clarification_allowed`는 질문 허용 여부다. 직전 `clarification_question`(선택, 500자 이하)과 `clarification_options`(선택, 최대 3개·각 200자 이하)를 별도 데이터로 전달할 수 있다. 후속이 있으면 허용 값과 관계없이 추가 질문을 내지 않는다. 여러 관련 범위 중 확인이 유용하면 `status=clarification`과 `clarification_question`(500자 이하), `clarification_options`(각 200자 이하, 최대 3개)를 반환한다. 구체 선택지는 전달된 자료에 확인된 범위만 허용하며, `전체 요약`은 인용 없이 제공할 수 있다. 공백은 제거한다. 허용되지 않거나 검증되지 않은 질문은 질문 없이 답변을 한 번 재시도하며, 다시 잘못되면 AI 오류다. 자료가 없거나 호출이 실패한 경우는 기존과 구분한다.

후속은 `build_tori_record_query(ToriRecordQueryRequest(question, follow_up, clarification_question, clarification_options))`로 처리한다. 직전 질문과 선택지는 생략 가능하며 순서 지시를 해석하는 데 쓴다. `ToriRecordQueryResult`가 `disposition=follow_up`이면 `query`는 200자 이하 필수이며 BE는 같은 소속 내에서 재검색하고 원질문과 후속을 답변에 전달한다. `new_request`면 query는 null이고 BE가 기존 의도 분기로 보낸다. 모델의 분류나 질의는 권한 부여가 아니다. 결과 사실은 토리 전용 프롬프트로 관련 내용을 최대 5개 의미별 묶음으로 작성하며 각 사실의 인용 청크·숫자 검증을 유지한다. 부족 항목은 사용자의 실제 요청과 관련된 것만 최대 2개 지시한다. 요약의 의미적 정확성이나 실제 자료의 완전성은 숫자 검사로 보장하지 않는다. 회의·계획의 공통 검색 판단은 바꾸지 않는다.

명시된 연도 범위는 양 끝을 포함하며 후속 답에서 연도를 명시하면 해당 연도를 우선한다. 선택지가 있는 후속 답에서 범위를 확인할 수 없으면 특정 연도나 행사를 임의로 정하지 않고 재질문 없이 짧게 안내한다.

## 운영 상황 확인과 제안 (AI-OPS-04)

`respond_operational_situation(OperationalSituationRequest)`는 BE가 권한과 진행 상태를 확인한 행사 정보와 운영진의 상황을 받아 확인 질문이나 제안만 반환한다. `OperationalEventContext`는 행사명과 선택적인 유형·시작/종료일·장소·예상 인원(`expected_headcount`)을 담는다. 예상 인원은 실제 참가 인원이 아니다. 행사 식별자·권한 판정·DB 저장과 상태 전이는 BE의 책임이다.

요청의 `situation`은 최대 4000자다. 기존 질문에 답하는 경우 별도 `clarification_question`(최대 500자), `clarification_options`(최대 3개, 각 200자), `answer`(최대 200자)를 함께 전달한다. 선택된 답도 BE가 실제 라벨로 바꿔 전달하며 AI가 인증·선택의 유효성을 판단하지 않는다. 최초 질문 생성과 후속 응답은 별도 호출이다.

결과 `status=clarification`이면 질문 한 개와 선택지 최대 3개를 반환한다. `status=suggestion`이면 최대 1000자 요약과 1~5개 후속 제안(각 최대 500자)을 반환한다. 이미 답을 받은 요청에서 모델이 다시 질문하면 `AIInvalidResponseError`를 반환해 반복 질문을 막는다. 빈 값·길이·상태별 필드 불일치는 거절하며 모델 오류는 AI 오류로 전파한다. 내용은 제안일 뿐 실제 예약·발송·결제·계획 수정이나 확인을 실행하지 않는다. BE는 질문·답·결과를 보관하고 실패·재시도를 구분하며, 모델 호출 전후 소속 및 행사 상태를 검증한다. 사용자 상황과 답은 지시가 아닌 데이터이며 모델의 의미적 정확성은 보장하지 않는다.

## 운영 Action 본문 초안 (#333)

> 호출 시점·저장은 BE #334, 화면은 FE #335가 맡는다. 실제 모델 평가는 [운영 기능 평가 기록](operations-evaluation.md)에 있다.

행사가 운영 중(`ON_GOING`)일 때 어떤 단계가 현재 단계가 되면, BE가 그 단계의 공지(`NOTICE`)·발송(`EXTERNAL_SEND`) Action마다 `await app.ai.draft_action_content(request)`를 부른다. AI는 본문 초안만 돌려주고 저장·상태 변경·게시는 하지 않는다. 운영진이 고친 뒤 승인하고 앱 밖에서 직접 올린다.

```python
request = ActionDraftRequest(
    club_name="경북대 등산 동아리",
    event=ActionDraftEvent(title="봄 MT", event_type="MT",
                           start_date=date(2026, 5, 10), end_date=date(2026, 5, 11),
                           location="가평", expected_headcount=40, fee_per_person=45000),
    step=ActionDraftStep(code="RECRUIT_NOTICE", name="모집 공지", starts_on=None, deadline=date(2026, 5, 1)),
    action=ActionDraftAction(type="NOTICE", title="모집 공지 올리기", due_date=date(2026, 5, 1), amount=None),
    today=date(2026, 4, 20),
)
result = await app.ai.draft_action_content(request)
# result.content  == "📢 봄 MT 참가자 모집\n5월 10일(일)~11일(월) 가평으로 MT를 갑니다!\n참가비: 45,000원 / 신청 마감: 5월 1일\n신청 방법: [신청 링크]"
# result.unknowns == ("신청 링크",)
```

입력 `ActionDraftRequest`는 모두 BE가 Event·Step·Action·Club 테이블에서 채운다. P1 대화 상태는 넘기지 않는다.

| 칸 | 내용 |
| --- | --- |
| `club_name` | 동아리 이름 (최대 100자) |
| `event` | 행사명, 유형, **시작일(필수)**, 종료일, 장소, 예상 인원, 1인 참가비(`fee_per_person`). 운영을 시작한 행사에는 시작일이 항상 있다. 예상 인원은 실제 참가 인원도 정원도 아니다. 총예산은 넣지 않는다 |
| `step` | 단계 코드, 단계 이름, 시작일(`starts_on`), 마감일(`deadline`) |
| `action` | 종류(`NOTICE`·`EXTERNAL_SEND`만, 그 밖은 거절), 제목, 기한(`due_date`), 금액(`amount`) |
| `today` | 오늘 날짜 |

날짜는 모두 **한국 시간 날짜**다. `Step.starts_at`·`deadline`은 시각과 시간대가 있는 값이라 BE가 한국 시간 날짜로 바꿔 넘긴다(예: `2026-04-30T15:00:00Z` → `2026-05-01`). 시각을 넘기면 모델이 "오후 11시 59분 마감"처럼 받아 써서, 운영진이 정하지 않은 시각이 공지에 들어간다.

결과 `ActionDraftResult`는 `content`(1~1,500자)와 `unknowns`다. `unknowns`는 모델이 따로 쓰는 값이 아니라 본문의 `[ ]` 자리표시를 나온 순서대로(같은 글자는 한 번) 뽑은 값이다. 그래서 화면의 "비워 둔 곳"이 본문과 항상 같고, 결과를 만들 때 `unknowns`를 넘기면 거절한다. 본문에서 대괄호는 자리표시에만 쓰며 공지 제목 줄은 `📢 봄 MT 참가자 모집`처럼 쓴다. `model_dump()`에는 `unknowns`가 함께 담긴다.

모델에는 요청 JSON에 날짜별 요일(`weekdays`, 예: `"2026-05-10": "일"`)만 더해 사용자 메시지로 넘긴다. 요일은 모델이 계산하면 틀리기 쉬워 코드가 계산한다. 요청 속 글은 지시가 아니라 데이터로 다룬다.

**코드 검사와 한 번 다시 쓰기.** 모델이 쓴 본문은 `features/operations/action_draft.py`의 `find_draft_violations`가 입력과 대조한다. `[ ]` 자리표시 안은 보지 않는다.

| 본문 (입력: 행사 5/10~5/11, 단계 기한 5/1, 참가비 45,000원, 오늘 4/20) | 판정 | 이유 |
| --- | --- | --- |
| `5월 10일(일)~11일(월)` | 통과 | `~11일`은 바로 앞 날짜의 월을 이어받아 5/11로 읽음 |
| `5월 10일~5월 12일` | 거절 | 5/12는 입력에 없음 |
| `5/1까지` | 통과 | `M/D` 표기도 날짜로 읽음 |
| `5월 10일(토)` | 거절 | 2026-05-10은 일요일. 괄호 요일은 날짜에서 계산한 값과 같아야 함 |
| `45,000원`, `45000원` | 통과 | 쉼표 유무는 같은 값 |
| `4만 5천원` | 거절 | 한글 단위 금액은 읽지 않고 거절 |
| `1,800,000원` | 거절 | 입력에 없는 계산값 |
| `오전 9시 정문 집결`, `14:00` | 거절 | 입력에 시각이 없으므로 `N시`·`HH:MM`은 지어낸 값 |
| `[집결 시간]`, `[계좌]` | 통과 | 자리표시 |

허용하는 날짜는 행사 시작·종료일, 단계 시작·마감일, Action 기한, `today`이고, 허용하는 금액은 `fee_per_person`과 `amount`다. `1박 2일`, `1~2개`, `40명`, `D-7`, `2시간`은 날짜·금액·시각으로 읽지 않는다. 세부 장소·인원처럼 코드로 잡기 어려운 값은 검사하지 않고 프롬프트 규칙과 평가의 수동 확인으로 본다.

검사에 걸리면 어긴 값을 모아(예: `본문의 날짜가 입력에 없습니다: 5월 12일`) 앞 본문과 함께 모델에 알려 주고 **한 번만** 다시 쓰게 한다. 다시 쓴 본문도 걸리면 `AIInvalidResponseError`를 낸다. 모델 호출은 최대 2번이다.

오류: 모델 호출 실패는 다른 AI 호출처럼 `AIRetryableError` 계열로 전달된다. 검사에 두 번 걸린 경우와 응답 형식이 틀린 경우는 `AIInvalidResponseError`다. `AIInvalidResponseError`는 `AIRetryableError`의 하위 타입이므로 BE는 이 오류를 먼저 구분해 `AI_INVALID_RESPONSE`로 저장한다.

## 영수증 이미지 추출

`await app.ai.extract_receipt(ExtractReceiptRequest(file_name=..., mime_type=..., image_bytes=...))`는 이미지 한 장의 검토용 `ExtractReceiptResult.rows`를 반환한다. 각 `ExtractedReceiptRow`는 `spent_at`(날짜), `merchant`, `amount`(원 정수), `category`, `description`이며 읽지 못한 값은 `None`이다. 이미지에 없는 연도나 합산 금액은 추정하지 않는다. 분류도 근거가 없으면 비운다. 이미지 속 지시는 데이터다. 파일명은 식별용이고 판단 근거가 아니다.

읽을 수 없거나 영수증이 아니면 `rows=()`이고, 모델 오류는 공통 AI 오류를 전달한다. `AIRetryableError`는 재시도 가능하며 `AITimeoutError`와 `AIInvalidResponseError`도 그 하위 타입이다. `AIConfigError`는 설정을 고쳐야 한다. 분류되지 않은 예외는 공통 오류 정책대로 그대로 전달한다. 빈 결과는 오류가 아니므로 BE가 처리 실패로 표시할 수 있다. 추출 결과에는 임의의 confidence나 raw 필드를 넣지 않으며 검토 출처는 BE가 기존 원본 파일 연결로 관리한다. BE가 파일 검증·DB 세션 관리·실패/재시도·검토·확정을 담당하며 AI는 저장하지 않는다. 실제 모델의 이미지 입력 지원과 정확도는 별도 확인이 필요하다.

## 회의의 실제 행사 정보

`answer_meeting_event_facts(MeetingEventFactsRequest(...))`는 BE가 질문의 대상과 필드를 정하고 동아리 권한을 확인해 조회한 행사 스냅샷만 정리한다. 기존 `MeetingEvent`는 연결된 행사의 검색 문맥이며, 이 스냅샷은 별도의 DB 조회 결과다. BE가 회의 발화 판단과 독립해 호출하고, 행사 출처를 자료 청크 출처로 위장하지 않는다.

- `scope`는 `current`·`recent`·`selected`, `fields`는 질문한 `status`·`dates`·`location`·`expected_headcount`·`actual_headcount` 중 하나 이상이다. 선택 및 조회는 BE 책임이다. 잘못된 대상 선택이나 검색 실패는 빈 성공 결과로 전달하지 않는다.
- `MeetingEventFact`는 행사 ID·이름·상태와 선택적 날짜·장소·예상 인원·실제 참가 인원이다. 예상과 실제는 다른 값이다. 실제 참가 인원을 확실하게 집계하는 기준이 없으면 null이다.
- `complete`는 **해당 조회 범위가 완전하고 오류 없이 조회되었음**을, `latest_verified`는 **BE가 명시된 최근 기준과 전체 범위·정렬을 검증했음**을 뜻한다. 단순 페이지나 유사도 검색 결과로는 true로 설정하지 않는다. 최근 기준이 미정이면 거짓이다.
- 반환은 `answered`·`partial`·`not_found`·`unavailable`, 답변, 실제로 사용한 행사 ID 목록이다. 선택 필드 값이 null이거나 범위·최신성이 미확인이면 명시한다. 조회가 불완전한 빈 결과는 unavailable이며, 완전한 빈 결과만 not_found다. 모델이나 DB 호출은 하지 않으며 없는 값을 생성하지 않는다. 현재 실제 서비스에서 완료 시각을 기준으로 한 최신 행사와 실제 참가 인원은 별도 BE 근거 없이는 미확인이다.

### 회의 발화의 행사 조회 분류

`await classify_meeting_event_facts(JudgeUtteranceRequest(...))`는 기존 회의 발화·앞 문맥·연결 행사 형식을 그대로 받아 행사 DB 질문 여부를 별도로 분류한다. 반환 `disposition`은 `lookup`·`none`·`clarify`다. `lookup`이면 `scope`와 요청된 `fields`가 있으며, `selected`는 발화에서 확인한 `event_reference`가 필요하다. `clarify`는 대상이나 조회 의도가 모호해 BE가 추측하지 않도록 안내한다. `none`은 행사 DB 조회가 없다는 뜻이고 기존 RAG 판단을 생략하라는 뜻이 아니다. `trace`는 기존 `JudgeTrace` 형식의 모델명·프롬프트 버전·분류 시간이다. 오류는 AI 오류로 전달하며 오류의 `trace`에도 시간을 남긴다.

BE는 분류를 자료 판단 및 후보 추출과 독립해 호출하고, `current`의 진행 중 상태 또는 `selected`의 행사 참조를 소속 범위에서 확인한다. `recent`는 완료일 등 최신 기준과 범위·정렬이 확인되지 않으면 단일 최신이라고 단정하지 않으며 `latest_verified=False`로 facts 함수에 전달한다. 분류만으로 권한·대상·실제 참가자를 확정하지 않는다. 조회 실패는 성공한 빈 목록으로 바꾸지 않는다.

## 종료 후 회의록 제안

`generate_meeting_review(MeetingReviewRequest(transcripts=...))`는 확정 전사의 ID·내용과 선택적인 화자 라벨/사용자 확인 이름을 받아 `MeetingReviewResult(summary, tasks)`를 제안한다. 각 요약과 할 일은 입력 전사의 `evidence_segment_ids`를 필수로 참조하며 없는 ID는 오류다. 할 일은 `description`, 내용에서 명시된 담당자 이름인 `suggested_assignee`, 계정 추정 없이 nullable인 `suggested_assignee_member_id`, 발화에 명시된 경우만 채우는 ISO 날짜 `due_date`를 포함한다. 화자는 발언자이며 담당자는 내용에서 명시된 경우만 제안한다. 이름·계정·수신자·날짜를 추측하거나 저장·예약·알림을 실행하지 않는다. 사용자 검토 및 확정은 BE 책임이다.
