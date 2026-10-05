# AI 오류 타입 (errors.py)

## 무엇인가

[`errors.py`](../errors.py)는 AI 처리에 실패했을 때 BE에 올리는 예외 타입을 정의한다.
AI는 실패를 빈 결과로 돌려주지 않고 예외로 알린다(AI-COMMON-02).
BE는 예외 타입을 보고 사용자에게 다시 시도를 안내할지, 서버 오류로 처리할지 정한다.
HTTP 상태와 FE 에러 코드로 바꾸는 일은 BE가 맡는다.

## 오류 타입

같은 요청을 다시 보냈을 때 성공할 수 있는지를 기준으로 나눈다.

```text
AIError
├── AIConfigError
└── AIRetryableError
    ├── AITimeoutError
    └── AIInvalidResponseError
```

| 타입 | 뜻 | BE 처리 |
| --- | --- | --- |
| `AIConfigError` | API 주소·키·모델명 등 설정 문제 | 재시도를 권하지 않는다. 설정을 고쳐야 한다 |
| `AIRetryableError` | 다시 시도하면 성공할 수 있는 오류 | 이 타입 하나로 재시도 안내 대상을 모두 잡는다 |
| `AITimeoutError` | 제한 시간 안에 응답을 받지 못함 | 모델 쪽 처리가 끝났을 수 있어 실행되지 않았다고 단정하지 않는다 |
| `AIInvalidResponseError` | 응답이 기대한 형식·계약 검증을 통과하지 못함 | 다시 생성하면 정상 응답이 나올 수 있다 |

예상하지 못한 예외는 `AIError`로 감싸지 않는다. 그대로 올려 BE가 서버 오류로 처리한다.

## 모델 호출 오류 변환

모델 호출 예외는 `llm.ainvoke_structured`가 위 타입으로 바꾼다. 기능 코드는 openai 예외를 직접 다루지 않는다.

| 실패 | 오류 |
| --- | --- |
| 응답 시간 초과 | `AITimeoutError` |
| 연결 실패·429·5xx | `AIRetryableError` |
| 401·403·404 (주소·키·모델명), 모델명 오류 400 | `AIConfigError` |
| 응답 형식 불일치·거절·빈 응답 | `AIInvalidResponseError` |
| 그 밖 (모델명 외 400 등) | 감싸지 않고 그대로 |

- 일시적 오류는 `DEFAULT_MAX_RETRIES`만큼 재시도한 뒤에 변환한다.
- 게이트웨이는 허용하지 않은 모델명에 404가 아니라 400으로 답한다. 본문의 `type`·`code`로는 다른 400과 구분되지 않아 문구(`MODEL_NOT_ALLOWED`)로 판별한다.
- 오류 메시지에는 고정 문구와 HTTP 코드만 넣는다. 응답 본문에 키나 요청 원문이 섞일 수 있어 원인 예외는 `__cause__`로만 연결한다.

## 호출할 때

`ainvoke_structured`는 실행 중인 이벤트 루프에서 `await`로 호출한다.
langchain-openai가 async HTTP 클라이언트를 프로세스에서 공유하므로, 호출마다 `asyncio.run()`을 쓰면
닫힌 루프의 연결을 다시 써서 실패한다. 이 오류는 분류 밖이라 그대로 올라간다.

## 관련 문서

- [AI 기능 요구사항](requirements.md): AI-COMMON-02 처리 실패를 알고 다시 시도하기
- [BE-AI 데이터 계약](contracts.md): `AIInvalidResponseError`의 기준이 되는 계약 검증
