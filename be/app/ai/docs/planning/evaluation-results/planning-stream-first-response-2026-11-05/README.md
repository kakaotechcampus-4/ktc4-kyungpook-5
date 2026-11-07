# 계획 대화 JSON·SSE 경로의 첫 반응 시간 — 2026-11-05

관련 [#266](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/266)(상위 [#262](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/262)), AI-PLAN-01, AI-PLAN-05, AI-COMMON-02.

토리 대화 지연 개선 4단계(SSE, PR #286)는 총시간을 줄이는 변경이 아니라 **화면이 처음 바뀌는 시각을 앞당기는 변경**이다. 이 측정은 그 효과를 제품 HTTP 경로에서 잰다.

> **첫 반응 시간**: 요청을 보낸 뒤 화면에 처음으로 무언가(진행 줄이나 답변 첫 글자)가 바뀔 수 있는 시각. JSON 경로는 응답이 다 와야 화면이 바뀌므로 첫 반응 = 전체 시간이다.

## 한 줄 결론

**두 사례 모두 채택 기준을 만족했다.** 첫 반응은 인원 변경에서 p50 6.34초 → 3.06초, 버튼 생성에서 11.72초 → 0.03초로 앞당겨졌다. 전체 시간 p50 차이는 인원 변경 −0.22초, 버튼 생성 +0.36초로 기준(+0.5초 이내) 안이다. 40건 모두 결과 검사를 통과했다.

```text
"예상 참가 인원을 60명으로 바꿔줘. 계획 초안은 만들지 마."   (p50)

JSON  0초 ──────────────────────────────── 6.34초  답변·조건이 한꺼번에
SSE   0초 ── 3.06초  • 조건을 반영하고 있어요            ← condition_started
                     ✓ 예상 인원 60명으로 변경했어요      ← condition_applied
              5.04초  토리 답변 첫 글자                  ← reply_delta
              6.11초  저장 완료, 화면 갱신               ← done

「흐름 만들기」 버튼   (p50)

JSON  0초 ─────────────────────────────────────── 11.72초  초안 표시
SSE   0초 ── 0.03초  • 계획 초안을 만들고 있어요          ← generation_started
              12.09초 저장 완료, 초안 표시                ← done
```

버튼 생성의 0.03초는 서버가 요청을 받아 생성을 시작했다는 알림이다. 초안 내용이 빨리 나온다는 뜻은 아니다. 생성 모델은 검증 전 초안을 보여 주지 않으므로(#266 설계), 버튼 생성에서 SSE가 바꾸는 것은 "요청이 처리 중인지 알 수 없는 시간"이 사라지는 것이다.

## 측정 전에 정한 채택 기준

[#266 착수 코멘트](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/266#issuecomment-6626081557)에 적은 초안을 측정 전에 아래로 확정했다(11-05).

- 사례: 인원 변경(C2)과 버튼 생성(G2). 진행 줄이 먼저 뜨는 효과가 가장 잘 보이는 두 경로다. 상담(C1)·채팅 생성(G1)은 비용을 줄이려고 재지 않았다.
- 같은 고정 시작 상태에서 JSON과 SSE를 번갈아 10라운드. 예열 4건은 집계에서 뺀다.
- **SSE 전체 시간 p50이 JSON보다 0.5초 넘게 늘지 않고, 결과 검사 통과가 JSON보다 적지 않으면 채택**한다.

## 실행 조건

| 항목 | 실제 기록 |
| --- | --- |
| 코드 | `b151b58`(develop `f966656` + 측정 스크립트), dirty=false |
| 실행 시간 | 2026-11-05 23:28:31~23:36:07, Asia/Seoul |
| 모델 | `gpt-5.6-luna`, 대화 `planning-agent-v8`, 생성 `planning-generation-v2`·추론 low. 설정은 develop 그대로 |
| 서버 | 로컬 BE 1프로세스(uvicorn, `--reload` 없음), 로컬 PostgreSQL. 운영 Caddy는 거치지 않음 |
| 시작 상태 | AI 측정기 고정 입력 [planning_latency.json](../../../../tests/fixtures/eval/planning_latency.json)의 `resume_state`. MT / 50명 / 참가비 25,000원 / 날짜·장소 명시적 미정 / 생성 권유 대기 |
| 요청마다 | 새 행사를 만들고 그 대화에 위 상태를 넣는다. 앞 요청의 결과가 다음 요청의 입력이 되지 않는다 |
| 순서 | 홀수 라운드 C2→G2·JSON→SSE, 짝수 라운드 G2→C2·SSE→JSON. 동시 요청 1, 요청 사이 1초 |
| 시각 | 측정 스크립트가 HTTP 응답 조각을 받은 시각(`perf_counter_ns`). 브라우저가 그리는 시간은 빠진다(#302에서 이벤트 수신 → 화면 갱신 12~21ms 관찰) |

## 결과

시간은 초, 각 칸 10건. p95는 선형 보간(R7)이다.

| 사례 / 경로 | 검사 통과 | 첫 반응 p50 / p95 | 답변 첫 글자 p50 | 전체 p50 / p95 |
| --- | --- | --- | --- | --- |
| C2 인원 변경 / JSON | 10/10 | 6.34 / 7.44 | - | 6.34 / 7.44 |
| C2 인원 변경 / SSE | 10/10 | **3.06** / 3.47 | 5.04 | 6.11 / 8.93 |
| G2 버튼 생성 / JSON | 10/10 | 11.72 / 13.02 | - | 11.72 / 13.02 |
| G2 버튼 생성 / SSE | 10/10 | **0.03** / 0.04 | (답변 없음) | 12.09 / 14.05 |

같은 라운드의 JSON·SSE 짝 10개로 본 비교:

| 사례 | 첫 반응이 SSE가 빠른 짝 | 전체가 SSE가 빠른 짝 | 전체 시간 차이(SSE − JSON) 중앙값 |
| --- | --- | --- | --- |
| C2 | 10 / 10 | 6 / 10 | −0.38초 |
| G2 | 10 / 10 | 3 / 10 | +0.35초 |

검사 항목(시간 측정 뒤 수행): C2는 인원 60명·나머지 조건 유지·`changedFields=["headcount"]`·인원 근거 `specified`·생성 없음·답변 있음. G2는 조건 유지·생성 `generated`·단계 저장(12~13단계)·답변 없음.

## 해석과 한계

- **C2 SSE의 p95(8.93초)는 6라운드 한 건(10.66초) 때문이다.** 이 요청은 진행 이벤트가 4개였다(다른 요청은 2개). 모델이 조건 변경 뒤 Tool을 한 번 더 고른 경우로, 답변 첫 글자가 9.72초에 왔다. SSE 전송 때문에 늘어난 시간이 아니라 모델 판단의 차이이며, 검사는 통과했다.
- **G2는 SSE의 전체 시간이 10짝 중 7짝에서 길었다(중앙값 +0.35초).** 두 경로는 같은 생성 함수를 부르고, SSE는 응답 헤더를 p50 22ms에 먼저 보낸 뒤 결과를 기다린다. 이 차이가 전송 방식 때문인지 생성 모델 응답의 흔들림인지는 **확인하지 않았다.** 기준(+0.5초) 안이라 더 파지 않았다.
- 1세션 10라운드다. 공급자 속도는 측정 시각마다 달라지므로(#263) 다른 날의 절대값과 비교하지 않는다.
- 로컬 서버에서 쟀다. 운영 Caddy 경유는 이 측정에 포함하지 않았다. 운영 화면에서 진행 줄이 답변보다 먼저 뜨는 것은 사용자가 확인했다(11-05).
- 끊김 뒤 다시 확인하는 경로(같은 Idempotency-Key 재요청)는 재지 않았다.

## 재현

`be/`에서, 같은 DB를 쓰는 BE 서버를 따로 켠 뒤 실행한다. 실제 모델을 부르므로 요청마다 비용이 든다. 결과 폴더는 저장소 밖에 새로 만든다.

```sh
# 1) 서버 (be/.env의 AI_* 필요)
DATABASE_URL=postgresql+psycopg://… .venv/bin/uvicorn app.main:app --port 8020
# 2) 측정 (계정은 동아리에 속해 있어야 한다. --club-id로 고를 수 있다)
DATABASE_URL=postgresql+psycopg://… .venv/bin/python scripts/measure_plan_stream_latency.py run \
  --api http://localhost:8020/api/v1 --email … --password … --out /저장소/밖/session-1 --rounds 10
# 3) 다시 집계 (모델 호출 없음)
.venv/bin/python scripts/measure_plan_stream_latency.py summarize evaluation-results/…/session-1
```

## 파일

- [session-1/session.json](session-1/session.json): 실행 조건(코드, 모델명, 순서, 기준값). 주소·키는 남기지 않는다.
- [session-1/attempts.jsonl](session-1/attempts.jsonl): 요청 44건(예열 4 포함)의 시각, 이벤트 수, 검사 결과, 토리 답변.
- [session-1/summary.json](session-1/summary.json): 위 표의 집계. 스크립트: [measure_plan_stream_latency.py](../../../../../../scripts/measure_plan_stream_latency.py)
