"""계획 대화·버튼 생성을 SSE로 흘려보낸다 (#266, #284).

요청 하나의 흐름:

    "인원 60명으로 바꿔줘" → planning_service.open_chat()  ← 멱등키·revision 확인(실패하면 일반 4xx)
      → stream(turn): AI 작업을 별도 asyncio 작업으로 실행
          AI가 포트로 알림 → 큐에 put_nowait → 여기서 한 줄씩 전송
            event: progress     {"operationId": …, "kind": "condition_applied", …}
            event: reply_delta  {"text": "예상 인원을 "}
          작업 끝 → event: done {PlanViewOut}  또는  event: error {code, message}

포트는 큐에 넣기만 한다. AI는 모델 응답을 읽는 루프 안에서 답변 조각을 알리므로,
여기서 네트워크 전송을 기다리면 모델 응답 읽기까지 멈춘다.

연결이 끊겨 이 생성기가 닫혀도 AI 작업은 별도 작업이라 끝까지 진행해 저장한다.
기존 JSON 경로도 연결이 끊겨도 끝까지 처리하므로 동작을 맞춘 것이다. FE는 POST를 다시
보내지 않고 GET /plan/requests/{key}로 저장된 결과를 조회한다(#342).
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import app.ai as ai
from app.core.exceptions import ApiError
from app.schemas.events import PlanProgressOut, PlanViewOut
from app.services.planning_service import PlanTurn, _draft_out

logger = logging.getLogger(__name__)

# 보낼 이벤트가 없을 때 주석 줄을 보내는 간격. 생성 모델은 10초 넘게 조용할 수 있어
# 프록시·브라우저가 유휴 연결로 보고 끊지 않게 한다.
HEARTBEAT_SECONDS = 15.0

# 실행 중인 AI 작업의 참조. asyncio는 작업을 약한 참조로만 들고 있어, 연결이 끊겨
# 생성기가 사라진 뒤 참조가 없으면 작업이 중간에 정리될 수 있다.
_running: set[asyncio.Task] = set()
_END = object()


class _QueuePort:
    """app.ai.PlanningProgressPort 구현. 이벤트를 SSE 줄로 바꿔 큐에 넣기만 한다."""

    def __init__(self, queue: asyncio.Queue) -> None:
        self.queue = queue
        self.closed = False  # 연결이 끊긴 뒤에는 쌓지 않는다.

    def _put(self, event: str, data: dict) -> None:
        if not self.closed:
            self.queue.put_nowait(_sse(event, data))

    async def progress(self, event: "ai.PlanningProgress") -> None:
        # 저장 결과와 같은 변환을 써서 메타 근거·날짜의 HTTP 형식을 맞춘다.
        data = event.model_dump(exclude={"condition_draft"})
        if event.condition_draft is not None:
            data["condition_draft"] = _draft_out(event.condition_draft)
        out = PlanProgressOut.model_validate(data)
        payload = out.model_dump(mode="json", by_alias=True)
        if event.condition_draft is None:
            payload.pop("conditionDraft")
        self._put("progress", payload)

    async def reply_delta(self, text: str) -> None:
        self._put("reply_delta", {"text": text})

    async def reply_reset(self) -> None:
        self._put("reply_reset", {})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _done(view: dict) -> str:
    # 기존 JSON 경로 응답의 data와 같은 모양(camelCase)이다.
    return _sse("done", PlanViewOut.model_validate(view).model_dump(mode="json", by_alias=True))


def _error(error: ApiError) -> str:
    return _sse("error", error.body()["error"])


def _internal_error() -> ApiError:
    return ApiError("요청을 처리하지 못했습니다. 계획을 다시 불러와 확인해 주세요.")


def _forget(task: asyncio.Task) -> None:
    _running.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if isinstance(error, ApiError):
        logger.info("계획 스트림 작업 실패: code=%s", error.code)
    elif error is not None:
        # 원문에는 사용자 대화가 섞일 수 있어 예외 정보는 서버 로그에만 남긴다.
        logger.error("계획 스트림 작업 예외", exc_info=error)


def _final(task: asyncio.Task) -> str:
    if task.cancelled():
        return _error(_internal_error())
    error = task.exception()
    if error is None:
        return _done(task.result())
    if isinstance(error, ApiError):
        return _error(error)
    return _error(_internal_error())


async def stream(turn: PlanTurn) -> AsyncIterator[str]:
    if turn.replay is not None:
        # 같은 키로 이미 끝난 요청이다. AI를 다시 부르지 않고 저장된 결과만 보낸다.
        yield _done(turn.replay)
        return

    queue: asyncio.Queue = asyncio.Queue()
    port = _QueuePort(queue)
    task = asyncio.create_task(turn.run(port))
    _running.add(task)
    task.add_done_callback(_forget)
    # 작업이 끝나면 큐에 끝 표시를 넣는다. 그 전에 넣은 알림은 모두 먼저 전송된다.
    task.add_done_callback(lambda _: queue.put_nowait(_END))
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if item is _END:
                break
            yield item
        yield _final(task)
    finally:
        # 연결이 끊겨 여기로 오면 작업은 취소하지 않고 알림만 버린다.
        port.closed = True
