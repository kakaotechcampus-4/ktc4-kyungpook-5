# 회의 자료 연결

확인 기준: 2026-10-19, 회의 베타 BE 작업의 실제 records 라우터·스키마. 인계 develop `0f97b2b` 이후 추가된 목록·색인 재시도 계약을 사용한다.

`RecordsPanel({ clubId: string })`은 팀 자료 목록을 조회하고 새 파일을 업로드하며 검색 준비 상태를 확인한다. 서버 실패를 fixture 성공으로 대체하지 않는다.

## 실제 요청

- `GET /api/v1/records?clubId=<id>`: 선택한 팀의 자료 목록. 현재 응답은 `Envelope<RecordOut[]>`이며 `meta`는 null이다. 전체 개수는 반환 배열 길이로 표시한다.
- `POST /api/v1/records`: multipart `clubId`, `category`, `file`. `eventId`는 선택이므로 팀 공통 자료에서는 생략한다. 업로드 시 파싱과 색인을 시도하며 실제 `parseStatus`를 반환한다.
- `GET /api/v1/records/{recordId}`: 상세·파싱 오류·처리 상태. 처리 대기/파싱 중/파싱 완료 상태는 화면이 열려 있는 동안 5초마다 확인한다. 조회 오류, `indexError` 또는 최종 상태에서는 자동 조회를 멈춘다.
- `POST /api/v1/records/{recordId}/index`: 파싱이 완료된 자료의 검색 준비 재시도. 실제 응답으로 목록/상세 cache를 갱신한다. HTTP 200이어도 `COMPLETED`와 `indexError`가 남으면 성공으로 표시하지 않는다.
- 인증, camelCase 응답 봉투, 오류는 `shared/api/client`를 그대로 사용한다.
- 타입은 실제 OpenAPI에서 생성된 `components`를 사용한다. 생성 파일을 직접 수정하지 않는다.

분류는 `RULES`, `EVENT_HISTORY`, `LEDGER`, `RECEIPT`, `ETC`다. 현재 파서가 읽는 PDF·CSV·XLSX만 파일 선택에 제공한다. 스캔 이미지·열람 암호 PDF는 처리 실패로 안내한다.

## 상태 의미

| 서버 상태 | 화면 의미 |
| --- | --- |
| `QUEUED` | 처리 대기 |
| `PARSING` | 내용 읽는 중 |
| `NEEDS_REVIEW` | 형식 확인 필요, 검색 준비 전 |
| `COMPLETED` | 파싱 완료, 검색 준비 전. `indexError`가 있으면 실패 안내·재시도 제공 |
| `INDEXED` | 검색 준비 완료 |
| `FAILED` | 처리 실패 |

파싱 실패 사유는 `parseError.reason`으로 안내하며 `debugMessage`는 UI에 노출하지 않는다. 검색 준비는 `INDEXED`에서만 완료로 표시한다. 권한은 서버가 소속을 검증한다.

## 확인

- `npm exec -- tsc -b --pretty false`: 통과.
- `npm exec -- eslint src/features/records`: 통과.
- 실제 파일 업로드·영구 색인 왕복은 실행 중인 BE와 인증 계정으로 별도 확인이 필요하다.
