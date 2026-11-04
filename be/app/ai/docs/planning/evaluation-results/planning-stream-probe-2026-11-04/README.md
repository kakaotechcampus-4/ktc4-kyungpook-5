# 계획 대화 스트리밍 형태 확인 (#280)

2026-11-04 KST. `8c0c40f` 위에서 `scripts/check_planning_stream.py`를 추가하고 기능 코드 변경 전에 실행했다. 스크립트 해시는 report.json에 있다. 입력은 기존 합성 지연 fixture와 제품 agent_messages/Tool 검증으로 구성했다. 원본 실행 위치는 작업 트리 밖 `/tmp/planning-stream-probe-280`이다.

## 조건과 결과

- 모델: gpt-5.6-luna. langgraph 1.2.12, langchain-core 1.6.3, langchain-openai 1.6.2, openai 3.16.2.
- 네 입력을 invoke/stream으로 번갈아 총 8회 호출. max_retries=0. 실제 Tool 실행/생성 모델/DB/제품 HTTP는 호출하지 않았다.
- 8회 모두 completed, invalid_tool_calls=0. 입력 29,065토큰, 출력 1,079토큰(공급자 보고값 합). 과금액은 미확인이다.
- 추론 원문·요약·암호화 본문은 보존하지 않았다. 해당 블록의 키 이름만 기록했다. 텍스트는 합성 입력의 사용자용 문장만 남겼다.

| 입력 | 관찰 |
| --- | --- |
| C1 현재 조건 설명 | 시작 text 블록에 final_answer, 후속 텍스트 delta에는 phase 없음. 최종 text ID는 나중에 도착 |
| C2 인원 변경+생성 보류 | 두 Tool 요청. 본문/인자를 SDK가 정상 조립. 사용자 답변 텍스트 없음 |
| C2-after-tool | 고정된 조건 변경 결과 뒤에도 생성 보류 Tool을 추가 요청. 최종 답변 사례로 세지 않음 |
| mixed 설명 후 변경 | commentary 텍스트 뒤 조건 변경 Tool. 최종 답변으로 보여주면 안 되는 실제 혼합 사례 확보 |

C1 스트림의 첫 텍스트 도착은 1,715.90ms, 전체 수신은 2,717.42ms였다. 표본 1건의 SDK 수신 관찰이다. UI 반응 시간이나 개선 p50이 아니며, invoke와 별도 호출한 결과의 문장/캐시 조건도 같지 않다. 성능 채택 기준의 증거로 사용하지 않는다.

## 결정

- phase를 블록별로 기억하고 final_answer만 점진 전달한다. commentary·추론·Tool 인자는 숨긴다.
- phase가 없거나 순서를 확정할 수 없으면 완료 검증까지 버퍼링한다. 이미 전달한 답변 뒤 Tool이 나오거나 수신이 실패하면 reset한다.
- SDK의 chunk 합산과 message_chunk_to_message를 사용한다. stream content의 전송용 index 제거, 누락된 빈 text annotations 보완이 필요하다. 의미 있는 content·Tool 인자/ID·phase는 보존한다.
- 공개 reply는 invoke/stream 공통으로 final_answer를 선택한다. 혼합 commentary는 저장 이력에 남기되 사용자 답변에는 합치지 않는다. phase가 없는 기존 메시지는 text를 유지한다.
- Graph 구조·모델 설정·프롬프트·생성 JSON은 변경하지 않는다.

## 공식 문서와 구현 방식

2026-11-04 [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)의 messages/custom, 노드·태그 필터링을 확인했다. 전체 그래프에서 모든 모델 출력을 받아 고르는 방식도 가능하지만, 대화와 생성 모델의 구분·공급자 완료 검증은 여전히 필요하다. #279의 포트를 유지하고 대화 모델 경계에서만 스트리밍하는 쪽을 선택했다. Graph는 기존 ainvoke와 최종 상태 반환을 유지한다.

[LangChain model streaming](https://docs.langchain.com/oss/python/langchain/models#stream)의 조각 합산 방식을 사용한다. SDK의 provider-specific phase 처리와 저장 형태 차이는 설치된 코드 및 위 실제 관찰로 확인했다.

## 재현과 검증 범위

```sh
cd be
.venv/bin/python -m app.ai.scripts.check_planning_stream --dry-run
# 유료 모델 호출 8회. 출력 디렉터리는 새 경로여야 한다.
.venv/bin/python -m app.ai.scripts.check_planning_stream --output /tmp/new-stream-probe
.venv/bin/python -m pytest app/ai/tests/test_planning_stream.py -q
```

실제 invoke/stream 호출은 확률적이므로 원문 동일성을 주장하지 않는다. 동일 원본에 대한 조립·저장·복원 동등성은 고정 응답 테스트로 검사한다. 다음 턴 Tool 이력 복원, 불완전 수신, callback 오류·취소를 포함한다. 제품 SSE·브라우저·재접속·성능 채택 측정은 후속이다.
