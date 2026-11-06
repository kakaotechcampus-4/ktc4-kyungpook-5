# 운영 Action 본문 초안 원문 (run1)

모델 `gpt-5.6-luna`, 프롬프트 `action-draft-v1`, 커밋 `7cdc89f`, 실행일 2026-11-06

## survey_full · DEMAND_SURVEY · NOTICE

검사: 첫 호출 통과, 호출 1번, 4.58초, 비어 있던 값: 없음, unknowns: 신청 링크

### 호출 1

```text
📢 겨울방학 해커톤 참여 의향 조사

일시: 12월 19일(토)~20일(일)
장소: IT대학 5호관

참여를 희망하시는 분은 11월 30일(월)까지 아래 설문에 응답해 주세요.
설문 링크: [신청 링크]
```

## survey_missing · DEMAND_SURVEY · NOTICE

검사: 첫 호출 통과, 호출 1번, 6.18초, 비어 있던 값: location, end_date, step.deadline, action.due_date, unknowns: 응답 방법

### 호출 1

```text
📢 새해 해맞이 산행 참여 의사 조사

일시: 1월 1일(금)
참가비: 15,000원

참여를 희망하시는 분은 [응답 방법]으로 알려 주세요. 아직 신청 접수가 아닌 참여 수요 조사입니다.
```

## recruit_full · RECRUIT_NOTICE · NOTICE

검사: 첫 호출 통과, 호출 1번, 4.23초, 비어 있던 값: 없음, unknowns: 신청 방법

### 호출 1

```text
📢 봄 MT 참가자 모집

일시: 3월 27일(토)~28일(일)
장소: 경주
참가비: 50,000원

신청 기한: 3월 19일(금)
신청 방법: [신청 방법]
```

## recruit_missing · RECRUIT_NOTICE · NOTICE

검사: 첫 호출 통과, 호출 1번, 3.71초, 비어 있던 값: location, end_date, step.deadline, action.due_date, unknowns: 장소 미정, 마감일, 신청 방법

### 호출 1

```text
📢 신입생 환영회 참가자 모집

일시: 3월 12일(금)
장소: [장소 미정]
참가비: 20,000원
신청 기간: [마감일]까지
신청 방법: [신청 방법]
```

## responses_full · CHECK_RESPONSES · NOTICE

검사: 첫 호출 통과, 호출 1번, 4.23초, 비어 있던 값: 없음, unknowns: 응답 방법

### 호출 1

```text
📢 벚꽃 피크닉 참여 여부 확인

일시: 4월 3일(토)
장소: 수성못

아직 참여 의사를 남기지 않은 분들은 3월 27일(토)까지 [응답 방법]으로 알려주세요.
```

## responses_missing · CHECK_RESPONSES · EXTERNAL_SEND

검사: 첫 호출 통과, 호출 1번, 3.12초, 비어 있던 값: location, end_date, step.deadline, action.due_date, fee_per_person, unknowns: 이름

### 호출 1

```text
[이름]님, 안녕하세요!
7월 10일(토) 여름 MT 참여 여부를 아직 확인하지 못해 연락드립니다.
참여 가능 여부를 회신해 주시면 감사하겠습니다.
```

## fees_full · COLLECT_FEES · NOTICE

검사: 첫 호출 통과, 호출 1번, 4.25초, 비어 있던 값: 없음, unknowns: 계좌

### 호출 1

```text
📢 가을 문학 기행 참가비 입금 안내

일시: 10월 24일(토)~25일(일)
장소: 통영
참가비: 70,000원

입금 기한: 10월 16일(금)
입금 계좌: [계좌]
기한 내 입금 부탁드립니다.
```

## fees_missing · COLLECT_FEES · EXTERNAL_SEND

검사: 첫 호출 통과, 호출 1번, 3.03초, 비어 있던 값: location, end_date, step.deadline, action.due_date, unknowns: 이름, 마감일, 계좌

### 호출 1

```text
[이름]님, 겨울 MT 참가비 입금 안내드립니다.
참가비는 40,000원이며, [마감일]까지 [계좌]로 입금 부탁드립니다.
행사는 1월 16일(토)에 진행될 예정입니다.
```

## pre_event_full · PRE_EVENT_NOTICE · NOTICE

검사: 첫 호출 통과, 호출 1번, 4.2초, 비어 있던 값: 없음, unknowns: 집결 시간, 집결 장소, 준비물

### 호출 1

```text
📢 별 관측 캠프 사전 안내

일시: 11월 21일(토)~22일(일)
장소: 영천 보현산

집결 시간: [집결 시간]
집결 장소: [집결 장소]
준비물: [준비물]
```

## pre_event_missing · PRE_EVENT_NOTICE · NOTICE

검사: 첫 호출 통과, 호출 1번, 4.13초, 비어 있던 값: location, end_date, step.deadline, action.due_date, fee_per_person, unknowns: 집결 시간, 장소 미정, 준비물

### 호출 1

```text
📢 정기 학술 발표회 사전 안내

일시: 12월 11일(금)
집결 시간: [집결 시간]
집결 장소: [장소 미정]
준비물: [준비물]
```

