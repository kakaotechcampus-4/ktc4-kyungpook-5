"""검증된 작업 결과를 일시적인 진행 문구로 바꾼다. 답변과 저장은 기존 경로가 맡는다."""

import logging

from ...contracts import PlanningProgress, RecordLookupResult, PlanGenerationResult
from ...ports import PlanningProgressPort
from .agent.tools import ConditionUpdateResult

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "title": "행사 이름", "event_type": "행사 종류", "headcount": "예상 인원",
    "fee_per_person": "참가비", "start_date": "일정", "end_date": "일정",
    "location": "장소", "budget_total": "총예산",
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


def generation_writing(operation_id: str) -> PlanningProgress:
    """생성 모델이 계획 JSON의 첫 글자를 보낸 순간(#388). 생성 시작과 같은 작업 ID라 화면은 같은 줄을 바꾼다.

    모델이 생각을 마쳤다고 따로 알려 주지 않아 첫 글자 도착을 그 순간으로 본다. 초안 내용은 싣지 않는다.
    실제 모델 20건에서 시작 신호 뒤 p50 4~5초에 왔고, 그 뒤 끝까지 p50 7~8초가 걸렸다.
    """
    return PlanningProgress(operation_id=operation_id, kind="generation_writing", status="running",
                            text="초안을 작성하는 중이에요")


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


def condition_progress(operation_id: str, result: ConditionUpdateResult) -> PlanningProgress | None:
    """검증된 조건 변경 → 항목 이름 요약 + 패널용 초안(#302).

    시작일·종료일은 「일정」 하나다. 값·잠정 여부는 초안과 답변이 전달한다.
    """
    if result.status != "applied" or not result.changed_fields:
        return None
    items = list(dict.fromkeys(FIELD_LABELS[field] for field in result.changed_fields))
    summary = " · ".join(items) if len(items) <= 3 else f"{' · '.join(items[:2])} 외 {len(items) - 2}개"
    return PlanningProgress(operation_id=operation_id, kind="condition_applied",
                            status="completed", text=f"{summary} 반영했어요",
                            condition_draft=result.draft)


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
