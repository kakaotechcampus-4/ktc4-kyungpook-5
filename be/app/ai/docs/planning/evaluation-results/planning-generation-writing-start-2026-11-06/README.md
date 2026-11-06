# 초안 생성의 「생각 중」과 「작성 중」 — 2026-11-06

관련 [#388](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/388), AI-COMMON-02, AI-PLAN-05.

초안 생성 화면의 「초안 작성」 구간을 실제 신호로 둘로 나누려 한다. 모델이 계획 JSON의 첫 글자를 보낸 순간을 기준으로 「토리가 생각 중이에요」와 「초안을 작성하는 중이에요」로 나눈다. 이 기록은 바꾸기 전에 두 구간이 실제로 얼마나 되는지 잰 것과, 바꾼 뒤 느려지지 않았는지 잰 것이다.

## 한 줄 결론

**두 구간 모두 충분히 길어서 진행했고, 바꾼 뒤 채택했다.** 바꾸기 전 측정에서 버튼 생성 기준 생각 중 p50 4.93초, 작성 중 p50 7.89초였다. 글자는 요청마다 850~979조각으로 나뉘어 6~8초에 걸쳐 고르게 왔다. 게이트웨이가 끝에 몰아서 보내지 않는다. 바꾼 뒤 전체 p50은 G2 +0.34초, G1 +0.30초로 기준 안이었다. G1 계획 검증 통과가 10 → 9인 점은 「채택 측정」 절에 원인과 함께 적었다.

```text
「이 조건으로 초안 만들기」 (G2, p50)

0초      generation_started        → 지금 화면: 계획 초안을 만들고 있어요
0.9초    응답 시작 조각 (글자 없음)
1.4초    추론 블록 시작 (글자 없음)
4.9초    계획 JSON 첫 글자 조각     ← 「생각 중」→「작성 중」을 바꿀 순간
         … 글자 조각 약 900개 …
12.8초   generation_finished
```

## 측정 전에 정한 기준

[#388 코멘트](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/388#issuecomment-6686807465)에서 측정 전에 정했다.

- 「작성 중」 구간 p50이 1초 미만이면(글자가 끝에 몰려 옴) 구현하지 않는다 → G2 7.89초, G1 7.42초로 통과
- 「생각 중」 구간 p50이 1초 미만이면 문구가 깜빡이는 문제를 다시 논의한다 → G2 4.93초, G1 4.07초로 통과

## 실행 조건

| 항목 | 실제 기록 |
| --- | --- |
| 코드 | `5fbb3c5`(develop, #387 머지 직후), 제품 코드 변경 없음(`product_code_dirty=false`) |
| 실행 시간 | 2026-11-06 23:11:47~23:17:57, Asia/Seoul |
| 모델 | `gpt-5.6-luna`, 생성 `planning-generation-v2`, 추론 low, 출력 한도 8192, 스트리밍. develop 설정 그대로 |
| 입력 | [planning_latency.json](../../../../tests/fixtures/eval/planning_latency.json)의 고정 상태(MT / 50명 / 25,000원 / 날짜·장소 미정 / 생성 권유 대기). 버튼 생성 G2는 `generate_planning_preview`, 채팅 생성 G1(“응, 만들어줘.”)은 `chat_planning`을 진행 포트와 함께 부름 |
| 순서 | 예열 G2·G1 각 1건(집계 제외) 뒤 10라운드. 홀수 라운드 G2→G1, 짝수 라운드 G1→G2. 요청 사이 1초 |
| 시각 | `perf_counter` 기준. 생성 모델에 기록용 콜백(`on_llm_new_token`)만 끼우고 제품 경로 `ainvoke_structured`는 그대로 탔다. DB·HTTP 없음 |

## 결과

시간은 ms. 생각 중 = `generation_started` 신호 → 첫 글자 조각, 작성 중 = 첫 글자 조각 → `generation_finished` 신호. p95는 선형 보간(R7)이다.

| 사례 | 생성 성공 | 생각 중 p50 (최소~최대) | 작성 중 p50 (최소~최대) | 글자 조각 수 p50 | 전체 p50 |
| --- | --- | --- | --- | --- | --- |
| G2 버튼 생성 | 10/10 | **4,927** (3,840~6,762) | **7,894** (6,887~8,815) | 908 | 12,790 |
| G1 채팅 생성 | 10/10 | **4,071** (3,579~5,021) | **7,416** (6,925~9,093) | 882 | 18,775 |

G1의 전체 시간에는 생성 전후의 대화 모델 호출 두 번이 들어 있다. 두 구간은 생성 모델 한 번 안의 값이라 G2와 같은 기준으로 읽는다.

생각 중 구간을 생성 모델 호출 안에서 나눠 보면 아래와 같다(20건, 최소 / p50 / 최대 ms).

| 구간 | 최소 | p50 | 최대 |
| --- | --- | --- | --- |
| 호출 시작 → 응답 시작 조각 | 713 | 934 | 3,030 |
| 응답 시작 → 추론 블록 시작 | 204 | 453 | 1,858 |
| 추론 블록 시작 → 첫 글자 | 1,887 | 2,794 | 4,020 |
| 마지막 글자 → 응답 끝 | 208 | 638 | 897 |

## 해석과 한계

- **이슈 작성 때 추정한 「생각 중 1~2초」보다 길다.** 응답 시작까지 약 0.9초, 추론 블록이 열린 뒤 첫 글자까지 약 2.8초가 걸렸다. 추론 토큰은 p50 약 250개다(#264의 low 측정과 비슷하다).
- 추론 블록 조각은 요청마다 2개였고 글자가 없었다. 게이트웨이가 추론 요약 글을 보내지 않는다. 그래서 「생각 중」 동안 보여 줄 실제 진행은 이 구간 안에 없다.
- 생성 모델 호출 안의 SDK 수신 시각이다. 제품 화면에서는 BE 준비와 SSE 전송만큼 모든 시각이 조금씩 늦다(#266 측정에서 첫 신호 p50 0.03초).
- 1세션 10라운드다. 공급자 속도는 측정 시각마다 달라지므로 다른 날의 절대값과 비교하지 않는다.
- 원본 `baseline-report.json`에는 모델이 쓴 글을 남기지 않았다. 블록 종류, 글자 수, 시각, 토큰 수만 있다.

## 채택 측정 (바꾼 뒤)

[측정 전에 정한 기준](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/388#issuecomment-6686807465): 같은 세션에서 기존 경로(`ainvoke_structured`)와 새 경로(`astream_structured`)를 번갈아 10라운드씩 잰다. 전체 시간 p50이 0.5초 넘게 늘지 않고, 계획 검증 통과 수가 줄지 않고, 새 경로의 모든 요청에서 `generation_writing`이 정확히 한 번 오면 채택한다.

| 항목 | 실제 기록 |
| --- | --- |
| 코드 | `2a3242e`(구현 커밋), 제품 코드 변경 없음(`product_code_dirty=false`) |
| 실행 시간 | 2026-11-06 23:27:04~23:39:13, Asia/Seoul |
| 경로 | 두 경로 모두 진행 포트를 넘긴다. 기존 경로는 `generation.model.astream_structured` 자리에 첫 글자 알림을 무시하고 `ainvoke_structured`를 부르는 함수를 잠시 끼운다(`measure_adoption.py`) |
| 순서 | 예열 4건(집계 제외) 뒤 10라운드. 라운드마다 사례 순서와 경로 순서를 뒤집는다 |

| 사례 / 경로 | 생성 성공 | 전체 p50 / p95 (ms) | `generation_writing` |
| --- | --- | --- | --- |
| G2 버튼 / 기존 | 10/10 | 11,998 / 13,781 | 0/10 |
| G2 버튼 / 새 | 10/10 | 12,341 / 13,362 | 10/10 정확히 한 번 |
| G1 채팅 / 기존 | 10/10 | 19,030 / 21,171 | 0/10 |
| G1 채팅 / 새 | **9/10** | 19,326 / 19,997 | 10/10 정확히 한 번 |

- 전체 p50 차이(새 − 기존): G2 +0.34초, G1 +0.30초. 기준(+0.5초) 안이다. 같은 라운드 짝 10개 중 새 경로가 빠른 짝은 두 사례 모두 5개다.
- 신호 순서는 새 경로 20건 모두 `generation_started → generation_writing → generation_finished`였다.
- **계획 검증 통과는 G1에서 10 → 9로, 측정 전 기준을 문자 그대로 읽으면 미달이다.** 실패 1건(라운드 6)은 응답을 끝까지 받고 형식 검사를 통과한 뒤, 내용 검사 `validate_plan`에서 `invalid_plan`으로 거절됐다. 두 경로가 게이트웨이에 보내는 요청 본문이 같다는 것을 가짜 서버로 확인했고, 이 사실을 `test_두_경로는_게이트웨이에_같은_요청을_보낸다`로 고정했다. 받는 방식은 모델이 쓰는 내용에 영향을 줄 수 없으므로 모델 출력의 흔들림으로 판단했다(추론). 같은 종류의 내용 검증 실패는 이전 측정에도 있었다(#239 18건 중 2건, #264 G2 low 30건 중 2건). 이 판단으로 채택하기로 사용자와 정했다(11-06).
- 원본: `adoption-report.json`. 모델이 쓴 글은 남기지 않았다.

## 재현

`be/`에서 실행한다. 실제 모델을 부르므로 요청마다 비용이 든다(예열 포함 생성 22회, G1은 대화 모델 호출도 함께).

```sh
# AI_* 환경변수 필요. 결과는 새 경로에 쓴다.
.venv/bin/python -I app/ai/docs/planning/evaluation-results/planning-generation-writing-start-2026-11-06/measure_writing_start.py /tmp/new-report.json 10
# 집계 (모델 호출 없음)
.venv/bin/python -I app/ai/docs/planning/evaluation-results/planning-generation-writing-start-2026-11-06/summarize.py /tmp/new-report.json
# 채택 측정: 기존·새 경로 번갈아 (예열 포함 생성 44회)
.venv/bin/python -I app/ai/docs/planning/evaluation-results/planning-generation-writing-start-2026-11-06/measure_adoption.py /tmp/new-adoption.json 10
.venv/bin/python -I app/ai/docs/planning/evaluation-results/planning-generation-writing-start-2026-11-06/summarize_adoption.py /tmp/new-adoption.json
```
