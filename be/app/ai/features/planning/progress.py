"""검증된 작업 결과를 일시적인 진행 문구로 바꾼다. 답변과 저장은 기존 경로가 맡는다."""

import logging
from datetime import date

from ...contracts import PlanningProgress, RecordLookupResult, PlanGenerationResult
from ...ports import PlanningProgressPort
from .agent.tools import ConditionUpdateResult

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "title": "행사 이름", "event_type": "행사 종류", "headcount": "예상 인원",
    "fee_per_person": "참가비", "start_date": "일정", "end_date": "일정",
    "location": "장소", "budget_total": "총예산",
}
EVENT_TYPES = {
    "MT": "MT", "WELCOME": "개총·신환회", "PICNIC": "피크닉",
    "ACADEMIC": "학술행사", "WORKSHOP": "워크샵", "ETC": "기타",
}


async def notify(port: PlanningProgressPort | None, event: PlanningProgress | None) -> None:
    if port is None or event is None:
        return
    try:
        await port.progress(event)
    except Exception:
        # 연결이 끊겨도 AI 결과를 잃지 않는다. 예외 원문에는 전송 데이터가 섞일 수 있다.
        # CancelledError는 잡지 않아 서버 작업 자체의 취소 정책은 호출자가 결정한다.
        logger.warning("계획 진행 알림 전달 실패: kind=%s", event.kind)


async def reply_delta(port: PlanningProgressPort, text: str) -> None:
    try:
        await port.reply_delta(text)
    except Exception:
        logger.warning("계획 답변 조각 전달 실패")


async def reply_reset(port: PlanningProgressPort) -> None:
    try:
        await port.reply_reset()
    except Exception:
        logger.warning("계획 임시 답변 초기화 알림 실패")


def started(operation_id: str, *, generation: bool = False) -> PlanningProgress:
    return PlanningProgress(
        operation_id=operation_id,
        kind="generation_started" if generation else "search_started", status="running",
        text="계획 초안을 만들고 있어요" if generation else "지난 행사 기록을 찾고 있어요",
    )


def condition_started(operation_id: str) -> PlanningProgress:
    """모델이 조건 변경 Tool을 쓰기 시작한 순간(#290). 값 조각은 아직 다 오지 않아 일반 문구만 쓴다.

    완료 알림과 같은 Tool 호출 ID를 써서, 화면은 같은 줄을 "…반영했어요"로 바꾼다.
    실제 모델 9턴에서 이 순간은 완료보다 1.2~2.3초(p50 1.8초) 먼저 왔다.
    """
    return PlanningProgress(operation_id=operation_id, kind="condition_started", status="running",
                            text="조건을 반영하고 있어요")


def condition_skipped(operation_id: str) -> PlanningProgress:
    """조건이 거절됐거나 바뀐 값이 없을 때. 화면은 진행 중 줄을 조용히 지우고, 이유는 답변이 설명한다."""
    return PlanningProgress(operation_id=operation_id, kind="condition_applied", status="skipped",
                            text="바뀐 조건이 없어요")


def _shown(field: str, value) -> str:
    """패널에서 읽는 값의 모양으로 보여 준다. 예: 40 → '40명', 0(참가비) → '무료'."""
    if value is None:
        return "미정"
    if field == "headcount":
        return f"{value:,}명"
    if field == "fee_per_person":
        return "무료" if value == 0 else f"1인 {value:,}원"
    if field == "budget_total":
        return f"{value:,}원"
    if field == "event_type":
        return EVENT_TYPES.get(value, value)
    if isinstance(value, date):
        return f"{value.year}년 {value.month}월 {value.day}일"
    # 이름·장소는 자유 입력이라 따옴표로 값의 경계를 보인다. 예: 장소 ‘가평 펜션’
    return f"‘{value}’"


def _period(start: date | None, end: date | None) -> str:
    """행사 기간을 한 덩어리로 적는다. 같은 해·같은 달이면 뒤쪽을 줄인다.

    (12/5, 12/6) → '2026년 12월 5일~6일', (12/31, 1/2) → '2026년 12월 31일~2027년 1월 2일',
    (12/5, None) → '2026년 12월 5일', (None, None) → '미정'.
    """
    if start is None and end is None:
        return "미정"
    if start is None:
        return f"~{_shown('end_date', end)}"
    if end is None or end == start:
        return _shown("start_date", start)
    if end.year != start.year:
        tail = _shown("end_date", end)
    elif end.month != start.month:
        tail = f"{end.month}월 {end.day}일"
    else:
        tail = f"{end.day}일"
    return f"{_shown('start_date', start)}~{tail}"


def condition_progress(operation_id: str, result: ConditionUpdateResult) -> PlanningProgress | None:
    """검증된 조건 변경을 '항목 값 반영했어요' 한 줄로 만든다(#290).

    "인원 40명, 12월 5일부터 6일까지로 해 줘" → "예상 인원 40명 · 일정 2026년 12월 5일~6일 반영했어요".
    바뀐 항목이 여럿이어도 값을 모두 적는다. 처음 정한 값과 바꾼 값을 구분할 정보가 없으므로
    '변경'이 아니라 '반영'이라고 쓰고, 이전 값은 화면의 조건 패널이 보여 준다.
    """
    if result.status != "applied" or not result.changed_fields:
        return None
    conditions = result.draft.conditions
    items = []
    for field in result.changed_fields:
        # 시작일·종료일은 패널의 「일정」 한 칸이라 한 항목으로 묶는다(#300). 둘 다 바뀌어도 한 번만 적는다.
        if field in ("start_date", "end_date"):
            if any(item.startswith("일정 ") for item in items):
                continue
            fields = ("start_date", "end_date")
            shown = _period(conditions.start_date, conditions.end_date)
        else:
            fields = (field,)
            shown = _shown(field, getattr(conditions, field))
        tentative = " (잠정)" if any(
            getattr(conditions, f) is not None
            and (meta := result.draft.condition_meta.get(f)) and meta.status == "tentative"
            for f in fields) else ""
        items.append(f"{FIELD_LABELS[field]} {shown}{tentative}")
    return PlanningProgress(operation_id=operation_id, kind="condition_applied",
                            status="completed", text=f"{' · '.join(items)} 반영했어요")


def search_finished(operation_id: str, result: RecordLookupResult) -> PlanningProgress | None:
    """검색 결과를 세 가지로 나눈다(#300).

    찾음 → completed(초록 체크), 자료 없음 → empty(회색 대시), 검색 실패 → failed.
    자료 없음은 검색이 정상으로 끝난 것이라 실패로 보이지 않게 하고, '찾았다'로도 읽히지 않게 한다.
    """
    if result.status == "rejected":
        return None
    status, text = {
        "available": ("completed", "참고할 기록을 찾았어요"),
        "not_found": ("empty", "맞는 기록이 없었어요"),
        "failed": ("failed", "기록을 검색하지 못했어요"),
    }[result.status]
    return PlanningProgress(operation_id=operation_id, kind="search_finished", status=status, text=text)


def generation_finished(operation_id: str, result: PlanGenerationResult) -> PlanningProgress:
    succeeded = result.status == "generated"
    return PlanningProgress(
        operation_id=operation_id, kind="generation_finished",
        status="completed" if succeeded else "failed",
        text=f"초안 {len(result.preview.steps)}단계를 만들었어요" if succeeded else "초안을 만들지 못했어요",
    )
