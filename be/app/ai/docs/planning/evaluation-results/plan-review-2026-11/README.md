# 계획 수정 검토 실제 모델 평가 (#177, AI-PLAN-07, 2026-11-01)

고정 케이스 6개를 `review_plan_edit`에 넣어 실제 모델 응답을 확인했다. 케이스는 [plan_review_cases.json](../../../../tests/fixtures/eval/plan_review_cases.json), 실행기는 [run_plan_review_eval.py](../../../../scripts/run_plan_review_eval.py)다. 케이스마다 1회씩 호출했다. 같은 입력을 반복하지 않아 결과 변동 폭은 측정하지 않았다(미측정). 키·설정 주소·요청 헤더는 기록하지 않았고 케이스 id, 지연, outcome, 항목만 남겼다.

```bash
docker compose exec -T api /app/.venv/bin/python -m app.ai.scripts.run_plan_review_eval \
  --out app/ai/docs/planning/evaluation-results/plan-review-2026-11 --label baseline
```

판정: `outcome`이 기대와 같고, `must_mention_codes`를 모두 언급하며, `must_not_mention_codes`는 언급하지 않으면 통과다. 기대 outcome이 `any`인 두 케이스는 자동 판정 대신 아래 수동 확인을 한다.

## 기준(프롬프트 수정 전): 4/6

| id | 기대 | 실제 | 언급 코드 | 지연(ms) | 판정 |
|---|---|---|---|---|---|
| survey_removed | issues | no_issues | - | 6507 | 불일치 |
| book_before_confirm | issues | issues | BOOK_VENUE, CONFIRM_DETAILS | 5311 | 통과 |
| fee_deadline_after_event | issues | issues | COLLECT_FEES | 4410 | 통과 |
| ai_excluded_readded | any | no_issues | - | 2970 | 통과 |
| harmless_reorder | no_issues | issues | ASSIGN_ROLES, RESEARCH_VENUE | 3918 | 불일치 |
| undecided_dates | any | issues | DEMAND_SURVEY | 6156 | 통과 |

원본: [results-baseline.json](results-baseline.json)

불일치 2건의 원인(추정, 1회 실행 기준):

- `survey_removed`: 수요 조사를 빼고 인원이 잠정인데도 no_issues였다. 지침에 "뺀 단계가 하던 확인이 다른 단계로 대신되는지 본다"는 기준이 없어, 모집 공지·신청 현황 확인이 참여 의향을 대신한다고 본 것으로 추정한다. 모델 내부 이유는 확인하지 않았다.
- `harmless_reorder`: 같은 준비 단계 안에서 서로 의존 없는 두 단계의 순서만 바꿨는데 "담당자 없이 시작한다"며 순서 문제로 짚었다. 지침에 순서를 짚는 기준이 없어 과하게 걱정한 것으로 추정한다.

## 프롬프트 수정 1회

두 실패에 공통인 일반 기준 두 줄을 `prompts/review.md`에 더했다. 처음 수정에는 `harmless_reorder`와 같은 단계 쌍(역할 분담·장소 조사)을 괄호 예시로 넣었는데, 평가 케이스와 겹쳐 그 케이스가 지침 예시를 시험하는 셈이 되므로 예시를 빼고 같은 6케이스를 다시 쟀다. 아래 수정 후 결과와 원본은 예시를 뺀 최종 지침의 재실행이다(예시가 있던 중간 실행은 보존하지 않았다).

- 단계를 뺐다면 그 단계가 하던 확인이 다른 단계로 대신되는지 보고, 대신되지 않고 관련 조건이 잠정·미정이면 걱정거리로 본다.
- 앞뒤 의존이 없는 단계끼리의 순서 바뀜은 걱정거리가 아니다. 한 단계의 결과가 다른 단계의 전제일 때만 순서를 짚는다.

## 수정 후 같은 6케이스 재실행: 자동 판정 5/6 일치

수동 확인 케이스 중 `undecided_dates`는 날짜 미정 언급이 빠져 부분 통과다(아래). 표의 `통과`는 자동 판정만이다.

| id | 기대 | 실제 | 언급 코드 | 지연(ms) | 판정 |
|---|---|---|---|---|---|
| survey_removed | issues | no_issues | - | 4059 | 불일치 |
| book_before_confirm | issues | issues | BOOK_VENUE, CONFIRM_DETAILS | 5583 | 통과 |
| fee_deadline_after_event | issues | issues | COLLECT_FEES, EVENT_DAY | 4584 | 통과 |
| ai_excluded_readded | any | no_issues | - | 2476 | 통과 |
| harmless_reorder | no_issues | no_issues | - | 1480 | 통과 |
| undecided_dates | any | issues | BOOK_VENUE, CHECK_RESPONSES, CONFIRM_DETAILS, DEMAND_SURVEY | 6609 | 통과 |

원본: [results-after-prompt.json](results-after-prompt.json)

| id | 수정 전 | 수정 후 |
| --- | --- | --- |
| survey_removed | 불일치(no_issues) | 불일치(no_issues) |
| book_before_confirm | 통과 | 통과 |
| fee_deadline_after_event | 통과 | 통과(COLLECT_FEES, EVENT_DAY, kind schedule) |
| ai_excluded_readded | no_issues | no_issues |
| harmless_reorder | 불일치(issues) | 통과(no_issues) |
| undecided_dates | issues(DEMAND_SURVEY) | issues(DEMAND_SURVEY, CHECK_RESPONSES, CONFIRM_DETAILS, BOOK_VENUE) |

한 번씩만 재서 `harmless_reorder`의 개선이 지침 때문인지 실행 간 변동인지는 구분하지 못한다.

## 남은 불일치와 수동 확인

- `survey_removed`는 수정 후에도 no_issues다. 같은 조건에 날짜 미정을 더한 `undecided_dates`는 수요 조사 누락을 짚으므로, 모델이 "인원 잠정"만으로는 걱정거리로 보지 않는 것으로 추정한다. 이 케이스에 맞춘 문구를 더하면 과적합이라 이번 작업에서는 더 고치지 않았다. 남은 한계다.
- 남은 한계: `survey_removed`의 누락, `undecided_dates`의 날짜 미정 언급 누락.
- `undecided_dates`(수동 확인): 메시지가 "약 25명이라는 잠정 인원"이라고 말하고, 모집 공지와 신청 현황 확인으로 보완될 수 있다는 조건부 표현을 써서 확정 사실처럼 쓰지 않았다. 날짜 미정은 이번 메시지에서 언급하지 않았다. 기준("날짜 미정·인원 잠정이라고 분명히 말하는지") 중 인원 잠정만 충족해 **부분 통과**다(outcome 일치, 인원 잠정 언급, 날짜 미정 언급 누락). 남은 한계다.
- `ai_excluded_readded`(수동 확인): 두 실행 모두 no_issues라 사용자의 재추가 의도를 거스르는 말투 문제는 없었다. 환불 단계를 다시 넣은 것을 걱정거리로 강제하지 않는 기대와 맞다.
- `fee_deadline_after_event`: 수정 전후 모두 마감이 행사 종료일(11-22)보다 늦다는 일정 문제를 짚었다. 입력의 행사 시작일은 11-21이며 메시지는 종료일을 기준으로 썼다.

## 지연

케이스별 약 1.5~6.6초(단일 호출, 위 표). 반복 측정이 아니라 p50/p95는 내지 않는다.
