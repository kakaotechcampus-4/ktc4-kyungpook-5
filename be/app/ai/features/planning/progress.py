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


# 숫자·영문 끝 글자를 읽었을 때 받침이 있는지(있으면 True, ㄹ이면 "rieul").
_DIGIT_ENDINGS = {"0": True, "1": "rieul", "2": False, "3": True, "4": False,
                  "5": False, "6": True, "7": "rieul", "8": "rieul", "9": False}
_LETTER_ENDINGS = {"L": "rieul", "R": "rieul", "M": True, "N": True}


def particle_to(value: str) -> str:
    """'가평'→'으로', 'MT'→'로', '5월 10일'→'로'. 받침이 없거나 ㄹ이면 '로'다."""
    last = value.rstrip()[-1:] or " "
    if "가" <= last <= "힣":
        ending = (ord(last) - ord("가")) % 28
        batchim = "rieul" if ending == 8 else ending != 0
    elif last.isdigit():
        batchim = _DIGIT_ENDINGS[last]
    else:
        batchim = _LETTER_ENDINGS.get(last.upper(), False)
    return "으로" if batchim is True else "로"


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


def condition_progress(operation_id: str, result: ConditionUpdateResult) -> PlanningProgress | None:
    if result.status != "applied" or not result.changed_fields:
        return None
    if len(result.changed_fields) > 1:
        labels = "·".join(FIELD_LABELS[field] for field in result.changed_fields)
        text = f"{labels} 항목을 변경했어요"
    else:
        field = result.changed_fields[0]
        label = FIELD_LABELS[field]
        value = getattr(result.draft.conditions, field)
        if value is None:
            text = f"{label} 항목을 미정으로 변경했어요"
        else:
            if field == "headcount":
                rendered = f"{value:,}명"
            elif field == "fee_per_person":
                rendered = "무료" if value == 0 else f"1인 {value:,}원"
            elif field == "budget_total":
                rendered = f"{value:,}원"
            elif field == "event_type":
                rendered = EVENT_TYPES.get(value, value)
            elif isinstance(value, date):
                rendered = f"{value.year}년 {value.month}월 {value.day}일"
            else:
                rendered = str(value)
            meta = result.draft.condition_meta.get(field)
            tentative = "잠정 " if meta and meta.status == "tentative" else ""
            # 값의 받침에 따라 어색한 '으로'를 붙이지 않도록 결과를 자연스럽게 나눈다.
            if field == "headcount":
                text = f"예상 인원을 {tentative}{rendered}으로 변경했어요"
            elif field == "fee_per_person" and value == 0:
                text = f"참가비를 {tentative}무료로 변경했어요"
            elif field in {"fee_per_person", "budget_total"}:
                subject = "참가비를" if field == "fee_per_person" else "총예산을"
                text = f"{subject} {tentative}{rendered}으로 변경했어요"
            else:
                shown = rendered if isinstance(value, date) else f"‘{rendered}’"
                text = f"{label} 항목을 {shown}{particle_to(rendered)} {tentative}변경했어요"
    return PlanningProgress(operation_id=operation_id, kind="condition_applied",
                            status="completed", text=text)


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
