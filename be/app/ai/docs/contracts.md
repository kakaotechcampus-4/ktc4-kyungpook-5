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

> 상태: AI 초안(2026-10-13). #113에서 BE와 합의하기 전이다.
> 합의 전에는 `contracts.py`에 옮기지 않고, 합의하면 코드로 옮긴 뒤 이 절은 사용 흐름 예시만 남긴다.

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
    text: str              # Whisper 원문. AI는 고치지 않는다
    started_at: datetime   # VAD 구간 시작
    ended_at: datetime     # VAD 구간 끝. 지연 측정에 쓴다


class JudgeUtteranceRequest(ContractModel):
    meeting_id: str
    club_id: str           # 이 회의가 볼 수 있는 기록 범위. BE가 권한을 확인한 값
    utterance: MeetingUtterance
    # 바로 앞 발화들. 순번 순서로 최대 MEETING_CONTEXT_UTTERANCES개
    context: tuple[MeetingUtterance, ...] = ()


class JudgeUtteranceResult(ContractModel):
    utterance_id: str
    kind: Literal["NO_LOOKUP", "ANSWER", "NOT_FOUND"]
    # 무엇에 대한 답인지. 검색어 구성 단계가 만든 검색어다. NO_LOOKUP이면 None
    question: str | None = None
    answer: str | None = None                # ANSWER일 때만
    sources: tuple[RecordSource, ...] = ()   # ANSWER일 때 하나 이상


# 문맥으로 실어 보낼 앞 발화 수. AI가 정하고 BE는 이 값을 따른다
MEETING_CONTEXT_UTTERANCES: int


async def judge_utterance(
    request: JudgeUtteranceRequest,
    *,
    records: RecordSearchPort,
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
│ 20,000원 (2025 회비 수납 장부 · 2~15행)
└ [닫기]
```

| 발화 (앞 발화) | 결과 | 화면 |
| --- | --- | --- |
| "작년 MT 때 숙소비 얼마 나왔지?" | `ANSWER` · "550,000원" · 출처 `2025 봄 MT 결과보고 · 2쪽 · 2. 예산` | 질문과 답, 출처 |
| "그때 인원은?" (앞: "작년 봄 MT 얘기인데") | `ANSWER` · question "2025 봄 MT 참가 인원" | 질문과 답, 출처 |
| "민수야 예약했어?" | `NO_LOOKUP` | 띄우지 않음 |
| "재작년 신환회 장소 어디였지?" (관련 기록 없음) | `NOT_FOUND` · question "2024 신환회 장소" | 기록에 없음 |
| "작년 회비 얼마였지?" 뒤 검색 중에 "점심 뭐 먹지" | `ANSWER` | 늦게 와도 질문과 함께 띄움 |
| 모델 호출 시간 초과 | `AITimeoutError` | 처리하지 못함 |

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
- 처리에 실패하면 빈 결과가 아니라 [AI 오류 타입](errors.md)을 올린다. BE는 `AIError`를 "처리하지 못함"으로 보여주고 다시 시도하지 않는다. 회의 듣기는 계속한다(AI-MEET-07).
- 음성 인식 실패는 BE에서 끝난다. AI를 부르지 않고 BE가 "처리하지 못함"으로 보여준다.
- 관련 기록이 없는 것은 실패가 아니라 `NOT_FOUND`다.

### 아직 정하지 않은 것

- port 주입 방식. 초안은 키워드 인자로 받는다. BE의 AI 초기화 방식과 맞춘다.
- 판단 기록(#117). 검색어·모델·프롬프트 버전을 결과에 담아 BE가 저장할지 #117에서 정한다.
- 제한 시간 값. 임베딩·검색·답변 생성 지연을 잰 뒤 정한다([측정 기록](meeting-evaluation.md)).
- `MEETING_CONTEXT_UTTERANCES` 값. 측정은 앞 2발화로 했고, #114에서 정한다.
- 답 작성은 기록 검색 `search_records`(#72) 위에 만든다. #72가 선행이다.
