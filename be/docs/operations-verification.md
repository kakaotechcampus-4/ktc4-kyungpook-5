# BE 운영 연결 확인

운영 DB의 상태 확인과 migration 실행은 별도 단계다. `deployment_preflight.py`는 연결된 DB의 Alembic revision 집합이 이미지 head와 같은지 및 pgvector 확장이 있는지만 확인하며 스키마를 변경하지 않는다. 변경 전 DB 대상과 백업의 복원 가능성을 확인한다. 승인된 동일 이미지에서 `uv run --no-sync alembic current`, `uv run --no-sync alembic heads`로 revision을 확인하고, 백업 후 `uv run --no-sync alembic upgrade head`를 실행한다. 적용 후 current와 `uv run --no-sync python deployment_preflight.py`, API `/api/v1/healthz`를 각각 확인한다. 로그에 DB URL이나 비밀을 출력하지 않는다. health 200은 migration이나 실제 기능 완료의 증거가 아니다.

자료는 업로드 201 후 parseStatus/indexError를 확인하고 GET 상세와 원본 다운로드의 크기 및 SHA-256을 원본과 비교한다. 다른 소속의 상세/다운로드·삭제는 403이어야 한다. 정상 삭제는 DB와 청크를 지운 후 원본 삭제를 시도한다. 원본 삭제 실패 시 `Record file delete failed` 경고가 남고 DB 삭제는 되돌리지 않으므로 저장소 orphan 점검이 필요하다. S3의 테스트 객체는 해당 테스트로 생성된 키만 정리한다.

예약은 `meeting-beta.md`의 확인·조회·변경·취소 API와 `expectedVersion` 및 명시적 timezone을 따른다. `/accept`는 예약 생성이 아니다. `WEB_PUSH_VAPID_PUBLIC_KEY`, `WEB_PUSH_VAPID_PRIVATE_KEY`, `WEB_PUSH_VAPID_SUBJECT`의 설정 여부만 안전하게 확인하고 값은 출력하지 않는다. `REMINDER_DISPATCHER_ENABLED=true`, `REMINDER_POLL_SECONDS`와 단일 서버 실행 여부를 확인한다. 지정 수신자의 구독을 등록한 뒤 명시적인 `/api/v1/push/test` 응답의 SERVICE_ACCEPTED/PARTIAL_FAILURE/FAILED와 예약 상태 PENDING/SENDING/SERVICE_ACCEPTED/FAILED/CANCELLED를 구분한다. `Reminder dispatch failed` 또는 `Reminder poll failed` 로그는 실패 조사 신호다. 서비스 접수는 기기 표시를 보장하지 않으며, 실제 기기 표시 확인이 있어야 수신 성공이다. SENDING에서 프로세스가 중단되면 중복 방지를 위해 자동 재발송하지 않는다.

회의 음성은 `meeting-audio.md`를 따른다. 기존 녹음 chunk가 있는 회의의 재시작은 AUDIO_RESUME_UNSUPPORTED다. 오디오 seq는 1부터 연속, 메타데이터와 binary는 짝을 이루며 시각과 크기가 연속이어야 한다. 중복·누락은 AUDIO_SEQUENCE_GAP, 잘못된 종료는 AUDIO_END_MISMATCH다. 재접속 시 저장 전사와 실패 구간을 확인하고 새 회의에서 녹음한다. 미확인 프레임 재전송·동일 회의 중복 없는 재개에는 영속 수신 확인 지점, 프레임 식별·재전송, 연결별 시간축과 종료/동시 접속 계약이 필요하며 현재 지원하지 않는다.
