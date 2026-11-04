"""검증된 작업 결과를 일시적인 진행 문구로 바꾼다. 답변과 저장은 기존 경로가 맡는다."""

import logging
from datetime import date

from ...contracts import PlanningProgress, RecordLookupResult, PlanGenerationResult
from ...ports import PlanningProgressPort
from .agent.tools import ConditionUpdateResult

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "title": "행사 이름", "event_type": "행사 종류", "headcount": "예상 인원",
    "fee_per_person": "참가비", "start_date": "시작일", "end_date": "종료일",
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


def condition_progress(operation_id: str, result: ConditionUpdateResult) -> PlanningProgress | None:
    """검증된 조건 변경을 '항목 값 반영했어요' 한 줄로 만든다(#290).

    "인원 40명, 12월 5일부터로 해 줘" → "예상 인원 40명 · 시작일 2026년 12월 5일 반영했어요".
    바뀐 항목이 여럿이어도 값을 모두 적는다. 처음 정한 값과 바꾼 값을 구분할 정보가 없으므로
    '변경'이 아니라 '반영'이라고 쓰고, 이전 값은 화면의 조건 패널이 보여 준다.
    """
    if result.status != "applied" or not result.changed_fields:
        return None
    items = []
    for field in result.changed_fields:
        value = getattr(result.draft.conditions, field)
        meta = result.draft.condition_meta.get(field)
        tentative = " (잠정)" if value is not None and meta and meta.status == "tentative" else ""
        items.append(f"{FIELD_LABELS[field]} {_shown(field, value)}{tentative}")
    return PlanningProgress(operation_id=operation_id, kind="condition_applied",
                            status="completed", text=f"{' · '.join(items)} 반영했어요")


def search_finished(operation_id: str, result: RecordLookupResult) -> PlanningProgress | None:
    if result.status == "rejected":
        return None
    text = {
        "available": "참고할 기록을 찾았어요",
        "not_found": "맞는 기록을 찾지 못했어요",
        "failed": "기록을 검색하지 못했어요",
    }[result.status]
    return PlanningProgress(operation_id=operation_id, kind="search_finished",
                            status="failed" if result.status == "failed" else "completed", text=text)


def generation_finished(operation_id: str, result: PlanGenerationResult) -> PlanningProgress:
    succeeded = result.status == "generated"
    return PlanningProgress(
        operation_id=operation_id, kind="generation_finished",
        status="completed" if succeeded else "failed",
        text=f"초안 {len(result.preview.steps)}단계를 만들었어요" if succeeded else "초안을 만들지 못했어요",
    )
