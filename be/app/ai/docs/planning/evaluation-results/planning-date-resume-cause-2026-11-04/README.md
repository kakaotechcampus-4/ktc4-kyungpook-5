# 날짜 보류 재개 실패의 원인과 Tool 여러 개 허용 재판정 — 2026-11-04

관련 [#274](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/274)(선행 [#265](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/265), 상위 [#262](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/262)), AI-PLAN-01·02.

#265에서 토리가 한 응답에 Tool을 여러 개 고르게 했더니(`multi`) 아래 발화의 통과가 하나만 고를 때(`single`)보다 낮아(11/13 → 7/13) 채택하지 않았다. 이번에는 실패한 응답에 실제로 무엇이 들어 있었는지 보고, 그 결과로 다시 판정했다.

```text
상황: 날짜 이야기를 보류해 둔 상태 (deferred_topics = [dates])
발화: "날짜는 다시 얘기하자. 인원은 60명으로 바꿔줘. 초안은 만들지 마."
기대: 인원 60명 반영 + 날짜 보류 풀기(resume_topics) + 생성 보류
```

## 한 줄 결론

**실패는 날짜 재개를 빠뜨린 것이 아니라 "다시 얘기하자"를 "나중에 다시 얘기하자"로 읽어 날짜를 다시 보류한 것이었다(single·multi 같은 모양). 분명한 재개 문장, 틀린 턴 다음의 정정, 기존 보류 대조 4종은 두 설정이 모두 10/10이어서 측정 전에 정한 기준대로 Tool 여러 개 허용을 켰다(`PARALLEL_TOOL_CALLS = True`).**

## 2단계: 실패한 응답의 Tool 인자

실행기가 대조 사례에서도 응답별 Tool 이름·인자·실행 결과(`tool_trace`)와 최종 답변을 남기게 고친 뒤(`74ed046`), 같은 문장을 single/multi로 번갈아 각 10번 쟀다.

| | single | multi |
| --- | --- | --- |
| 통과 | 7/10 | 7/10 |
| 실패의 날짜 처리 | 다시 보류 3 | 다시 보류 3 |
| 빠뜨림(`omitted`) / 거절(`resume_rejected`) | 0 / 0 | 0 / 0 |

```text
통과  update_event_conditions(changes=[인원 60], resume_topics=[dates ← "날짜는 다시 얘기하자."])
      답변 "날짜 논의는 다시 이어갈 수 있도록 했고, 초안 생성은 보류할게요."
실패  update_event_conditions(changes=[인원 60], defer_topics=[dates ← "날짜는 다시 얘기하자"])
      답변 "날짜는 나중에 다시 논의하고, 준비 순서 초안은 지금 만들지 않을게요."
```

- 실패한 답변은 모두 "나중에"라고 말해 상태와 맞았다. 사용자가 답변을 보고 토리가 어떻게 이해했는지 알 수 있다.
- "할 일이 세 가지라 한 응답에 적을 때 날짜 재개를 빠뜨린다"는 #265의 추측은 맞지 않았다.
- #265부터 이 문장의 결과를 합치면 single 18/23, multi 14/23이다. 이 차이는 우연으로도 나올 수 있는 크기다(피셔 정확 검정 양측 p ≈ 0.34).
- "다시 얘기하자"는 "지금 다시"와 "나중에 다시"로 모두 읽히고 실제로 잘 쓰지 않는 표현이라, 이 문장은 기록만 하고 판정에서 뺐다(`AMBIGUOUS_CASE_IDS`). 기대값은 이전 점수와 비교할 수 있게 그대로 둔다.

## 3단계: 분명한 재개와 정정으로 재판정

모호한 표현을 잘못 읽는 것은 사용자가 답변을 보고 바로잡을 수 있으면 어느 정도 허용한다. 대신 분명하게 말했거나 정정했는데 틀리면 안 된다. 이 기준으로 사례 두 개를 더했다(`03c2ddd`).

| 사례 | 시작 상태 | 발화 |
| --- | --- | --- |
| `date_resume_clear` | 보류 [dates] | "이제 날짜 정하자. 인원은 60명으로 바꿔줘. 초안은 만들지 마." |
| `date_resume_correction` | 2단계에서 실제로 틀린 턴의 다음 상태(인원 60, 보류 [dates], 생성 보류, 답변 "날짜는 나중에 다시 논의하고 …"). [저장 파일](../../../../tests/fixtures/eval/planning_date_resume_correction.json) | "아니, 날짜는 지금 정하자는 거였어." |

채택 기준은 측정 전에 [#274 코멘트](https://github.com/kakaotechcampus-4/ktc4-kyungpook-5/issues/274#issuecomment-6624686523)에 적었다.

| 기준 | single | multi | 판정 |
| --- | --- | --- | --- |
| ① 분명한 재개: multi 9/10 이상, single 이상 | 10/10 | 10/10 | 만족 |
| ② 정정: multi 9/10 이상, single 이상 | 10/10 | 10/10 | 만족 |
| ③ 보류 대조 4종: multi가 2건 이상 낮지 않음 | 생성 보류 표현 변형·날짜 보류·날짜와 장소 보류·"그건 나중에" 각 10/10 | 각 10/10 | 만족 |
| ④ 모호한 `date_resume`: 기록만 | 9/10 | 8/10 | — |
| ⑤ 속도·호출 수: #265 C2 결과 | 호출 3번, p50 7.19초, 30/30 | 호출 2번, p50 6.17초, 30/30 | 만족 |

⑤는 다시 재지 않고 #265 결과를 썼다. 그 뒤로 지시문(`planning-agent-v8`), Tool 스키마, `tools_node`가 같다.

- multi는 Tool이 둘 필요한 사례에서 대부분 한 응답에 묶었다(사례마다 8~10/10). 정정은 Tool이 하나라 두 설정 모두 응답 1번이었다.
- 판정에 쓰지 않는 참고값: 대조 사례의 요청 p50은 multi가 0.7~2.2초 짧았다(정정은 4.32 / 4.43초로 같음). 사례마다 10건이고 시각이 한 번뿐이라 속도 근거로는 #265 C2를 쓴다.
- `date_resume`의 실패 3건(single 1, multi 2)도 모두 다시 보류였다.

## 따로 본 것

- **상태와 반대로 말한 답변.** 모호한 `date_resume`에서만, 두 설정 모두에서 나왔다(2단계 multi 1, 3단계 single 2·multi 1). 상태는 날짜를 재개했는데 답변은 "날짜는 나중에 다시 논의하고"라고 했다. 분명한 재개와 정정에서는 없었다. 검사기(`inspect_boundary`)는 상태만 보므로 통과로 센다. `analysis.json`의 `resumed_but_reply_mentions_later`가 "나중"이 든 답변을 고른 것이고, 사람이 읽어 확인했다.
- multi 답변 1건에 한자가 섞였다("暂시 미뤄둘게요", 3단계 `date_resume`). 한 번 나온 출력 오류로 기록만 한다.

## 실행 조건

| 항목 | 2단계 | 3단계 |
| --- | --- | --- |
| 기준 코드 | `74ed046`, dirty=false | `03c2ddd`, dirty=false |
| 실행 시간 (Asia/Seoul) | 15:32~15:35 | 15:56~16:14 |
| 모델 | `gpt-5.6-luna`, `planning-agent-v8`, temperature/reasoning 미설정, timeout 60초 | 같음 |
| 바꾼 것 | `nodes.PARALLEL_TOOL_CALLS`만(요청마다 바꿔 끼움) | 같음 |
| 요청 | `date_resume` × 2변형 × 10 = 20 | 대조 7종 × 2변형 × 10 = 140. 라운드마다 변형 순서를 뒤집음 |
| 오류 | 0 | 0 |

## 파일과 재집계

| 파일 | 내용 |
| --- | --- |
| `step2-date-resume/`, `step3-controls/` | `session.json`(프로필, 코드·입력·지시문 해시, 집계), `attempts.jsonl`(요청별 started/finished, `tool_trace`, `reply`, `dates_handling`, 공개 결과 전체) |
| [analysis.json](analysis.json) | 위 표의 값과 실패 요청의 인자·답변 |
| [analyze.py](analyze.py) | 원본에서 analysis.json을 다시 계산하는 오프라인 스크립트 |

결과는 작업 트리 밖에 쓴 뒤 이 폴더로 복사했다. 키, 인증 헤더, 설정 주소가 결과 파일에 없는지 확인했다.

```sh
# be/에서. 모델·API 설정을 쓰지 않는다.
.venv/bin/python app/ai/docs/planning/evaluation-results/planning-date-resume-cause-2026-11-04/analyze.py --output /tmp/planning-date-resume-analysis.json

# 다시 재려면 실제 모델 설정이 필요하다. 결과 폴더는 작업 트리 밖에 둔다.
.venv/bin/python -m app.ai.scripts.compare_parallel_tool_calls --output-dir <작업 트리 밖 폴더>/controls \
  --session-id controls --rounds 0 --no-warmup --controls 10
```

## 해석의 한계

- 사례마다 10번이다. 10/10과 9/10의 차이는 구분하지 못한다. 기준은 "분명한 말과 정정에서 거의 틀리지 않는가"를 본 것이다.
- 분명한 재개 문장은 하나("이제 날짜 정하자")다. 다른 분명한 표현, 날짜 외 주제(장소 등)의 재개는 재지 않았다.
- 정정은 한 턴만 봤다. 정정 뒤 날짜를 실제로 정하는 다음 턴은 재지 않았다.
- 답변과 상태의 불일치는 검사기가 잡지 않는다. 모호한 문장에서만 보였고 두 설정에 모두 있었다.
