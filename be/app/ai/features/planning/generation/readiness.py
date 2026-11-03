"""화면과 실제 생성이 공유하는 결정론적 최소 조건."""
from typing import Literal
from ..agent.state import PlanningDraft
from .schemas import PlanningGenerationState

GenerationBlock = Literal['event_type_missing', 'dates_unanswered', 'headcount_unanswered',
                          'location_unanswered', 'condition_change_pending']
BLOCK_MESSAGES = {
    'event_type_missing': '어떤 행사인지 먼저 정해 주세요.',
    'dates_unanswered': '행사 일정이 어떻게 되나요? 아직 미정이라고 답해도 괜찮아요.',
    'headcount_unanswered': '예상 인원은 몇 명인가요? 아직 미정이라고 답해도 괜찮아요.',
    'location_unanswered': '행사 장소는 어디인가요? 아직 미정이라고 답해도 괜찮아요.',
    'condition_change_pending': '반영하지 못한 조건 변경이 있어요. 현재 남은 조건으로 만들지 먼저 확인해 주세요.',
}


def generation_blocks(draft: PlanningDraft, state: PlanningGenerationState, *,
                      use_current_conditions: bool = False) -> tuple[GenerationBlock, ...]:
    blocks: list[GenerationBlock] = []
    if draft.conditions.event_type is None:
        blocks.append('event_type_missing')
    else:
        # 명시적으로 미룬 주제는 값 없이 보존하며 다시 답을 강제하지 않는다.
        for topic, field, reason in (
            ('dates', 'start_date', 'dates_unanswered'),
            ('headcount', 'headcount', 'headcount_unanswered'),
            ('location', 'location', 'location_unanswered'),
        ):
            if getattr(draft.conditions, field) is None and topic not in draft.deferred_topics:
                blocks.append(reason)
    if state.condition_change_pending and not use_current_conditions:
        blocks.append('condition_change_pending')
    return tuple(blocks)
