# BE-AI 데이터 계약 (contracts.py)

## 무엇인가

[`contracts.py`](../contracts.py)는 BE와 AI 모듈이 같은 프로세스 안에서 주고받는
요청·결과의 형식을 정의한다. DB 모델이나 FE 공개 API 스키마가 아니라,
`app.ai` 경계를 위한 내부 계약이다.

행사 계획(조건 수집·계획안 생성)과 기록 색인에 필요한 타입을 정의한다.
기록 색인은 `app.ai.index_record`로 호출하고, 계획 공개 함수는 BE와 합의한 뒤 제공한다.

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

result = await app.ai.index_record(request)

save_chunks(record, result.chunks)  # 메타데이터를 붙여 저장, INDEXED로 변경
```

`parse_result` 형식은 [예시 기록](../tests/fixtures/records/README.md)을 기준으로 한다.
블록마다 본문과 원문 위치(`location.label`)를 두며, 이 위치가 답변의 출처로 그대로 쓰인다.
