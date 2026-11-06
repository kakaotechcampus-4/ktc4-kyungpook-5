# 운영진 베타 운영 체크리스트

이 문서는 데스크톱 Chrome에서 운영진이 자료와 회의 내용을 확인하고, 근거 있는 할 일 후보를 저장하는 골든 패스를 재현하기 위한 최소 runbook이다. 모바일·일반 회원 기능은 이 베타 범위에 포함하지 않는다.

## 골든 패스

1. 운영진 계정으로 로그인하고 대상 소속을 선택한다.
2. 자료함에서 PDF/CSV 한 건을 업로드하거나, 시연 전용 fixture를 준비한다.
3. 회의를 생성하고 전사를 확인한다.
4. 전사에서 파생된 후보의 원문과 자료 출처를 확인한다.
5. 후보를 `PROPOSED` 상태로 저장한다. 자동 확정·알림 발송으로 간주하지 않는다.
6. 새로고침 또는 재로그인 후 같은 자료·회의·후보를 다시 조회한다.

## 시연 fixture 준비와 초기화

fixture는 기존 운영진 계정과 소속을 사용한다. 계정 생성, 비밀번호 저장, 토큰 발급, AI/임베딩 provider 호출, Push 접수는 하지 않는다. `--dry-run`이 기본이며, 같은 `demo-key`가 이미 있으면 중복 생성하지 않는다.

```bash
cd be

# 권한·중복·생성 항목만 확인
uv run python scripts/seed_meeting_demo.py \
  --account-id "$OWNER_ACCOUNT_ID" \
  --manager-account-id "$MANAGER_ACCOUNT_ID" \
  --club-id "$CLUB_ID" \
  --demo-key meeting-beta-1

# 두 운영진이 같은 소속을 조회할 수 있는 기준 fixture 생성
uv run python scripts/seed_meeting_demo.py \
  --account-id "$OWNER_ACCOUNT_ID" \
  --manager-account-id "$MANAGER_ACCOUNT_ID" \
  --club-id "$CLUB_ID" \
  --demo-key meeting-beta-1 \
  --due-date 2026-11-14 \
  --apply

# 해당 demo-key로 만든 자료·회의·전사·후보만 제거
uv run python scripts/seed_meeting_demo.py \
  --account-id "$OWNER_ACCOUNT_ID" \
  --club-id "$CLUB_ID" \
  --demo-key meeting-beta-1 \
  --rollback
```

`OWNER_ACCOUNT_ID`, `MANAGER_ACCOUNT_ID`, `CLUB_ID`는 배포 환경에서 확인한 식별자만 셸 변수로 주입한다. 계정 이메일·비밀번호·API 키를 저장소나 문서에 적지 않는다.

## 베타에서 약속하지 않는 것

- `?demo` 화면의 예시 데이터는 실서비스와 분리되며 예약·알림·외부 발송을 실행하지 않는다.
- 실제 Push를 테스트 기기에서 수신하기 전에는 “알림 발송 완료”를 약속하지 않는다.
- 화자 자동 분리는 provider 응답과 저장 결과를 별도로 확인하기 전까지 베타의 성공 조건으로 삼지 않는다.
- 모바일 녹음과 일반 회원 self-service는 지원 범위가 아니다.

## 오류가 난 경우

자료 파싱·검색 준비·전사·AI 답변·후보 저장·예약은 서로 다른 상태로 확인한다. 한 단계가 실패해도 기존 자료·전사·후보를 삭제하지 않고, 해당 단계의 재시도 또는 운영자 조치를 선택한다. fixture 생성 중 오류가 나면 명령이 저장소 파일을 정리하고 실패를 반환하므로, 같은 `demo-key`로 다시 `--dry-run`부터 실행한다.
