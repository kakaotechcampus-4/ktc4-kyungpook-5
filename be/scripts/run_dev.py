"""Windows 로컬 개발 서버 실행.

Windows의 기본 이벤트 루프(ProactorEventLoop)는 psycopg 비동기 드라이버와
맞지 않는다 (`Psycopg cannot use the 'ProactorEventLoop' ...`). 이 문제는
mock 전용이던 동안은 드러나지 않았고, 실제 DB를 쓰는 라우터가 생긴 지금
처음 걸린다(#131).

`uv run uvicorn app.main:app --reload`의 `--loop` CLI 옵션은 선택지가
고정돼 있어 커스텀 이벤트 루프를 못 넘긴다. uvicorn.run()의 Python API는
임의의 "module:attr" 문자열을 받으므로 여기서 직접 호출한다.

macOS/Linux는 이 문제가 없어 기존 `uv run uvicorn app.main:app --reload`를
그대로 써도 된다.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        loop="asyncio:SelectorEventLoop",
    )
