"""화면과 실제 생성이 공유하는 결정론적 최소 조건."""
from typing import Literal
from ..agent.state import PlanningDraft
from .schemas import PlanningGenerationState

GenerationBlock = Literal['event_type_missing', 'condition_change_pending']
BLOCK_MESSAGES = {
    'event_type_missing': '어떤 행사인지 먼저 정해 주세요.',
    'condition_change_pending': '반영하지 못한 조건 변경이 있어요. 현재 남은 조건으로 만들지 먼저 확인해 주세요.',
}


def generation_blocks(draft: PlanningDraft, state: PlanningGenerationState, *,
                      use_current_conditions: bool = False) -> tuple[GenerationBlock, ...]:
    blocks: list[GenerationBlock] = []
    if draft.conditions.event_type is None:
        blocks.append('event_type_missing')
    if state.condition_change_pending and not use_current_conditions:
        blocks.append('condition_change_pending')
    return tuple(blocks)
