"""#196: 반복마다 같은 JSON 상태에서 새 공개 요청을 만든다. 모델은 호출하지 않는다."""

import hashlib
import json
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from app.ai import PlanningChatRequest, PlanningPreviewRequest, PlanningResumeState, parse_resume_state
from app.ai.contracts import ContractModel, NonBlankStr, PlanningConditions
from app.ai.features.planning.state_codec import restore_history

AI_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = AI_DIR / 'tests/fixtures/eval/planning_latency.json'
CASE_IDS = ('C1', 'C2', 'G1', 'G2')


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value) -> str:
    return hashlib.sha256(json_text(value).encode()).hexdigest()


class LatencyCase(ContractModel):
    id: Literal['C1', 'C2', 'G1', 'G2']
    message: NonBlankStr | None = None
    expected_headcount: int | None = Field(default=None, strict=True, gt=0)

    @model_validator(mode='after')
    def validate_case(self) -> Self:
        if (self.id == 'G2') != (self.message is None):
            raise ValueError('버튼에는 발화가 없고 채팅에는 발화가 필요합니다')
        if (self.id == 'C2') != (self.expected_headcount is not None):
            raise ValueError('조건 변경 사례에만 목표 인원이 필요합니다')
        return self


class LatencyFixture(ContractModel):
    fixture_version: Literal[1]
    provenance: NonBlankStr
    actual_provider_calls: Literal[0]
    reference_date: Literal['2026-10-28']
    timezone: Literal['Asia/Seoul']
    base_revision: int = Field(strict=True, ge=0)
    resume_state: PlanningResumeState
    cases: tuple[LatencyCase, ...]

    @model_validator(mode='after')
    def validate_starting_point(self) -> Self:
        if len(self.cases) != 4 or {case.id for case in self.cases} != set(CASE_IDS):
            raise ValueError('네 가지 사례가 중복 없이 필요합니다')
        state = self.resume_state
        draft, generation = state.payload.basis_draft, state.payload.generation
        if draft.conditions != PlanningConditions(event_type='MT', headcount=50, fee_per_person=25000):
            raise ValueError('기준 조건은 MT, 50명, 참가비 25000원, 나머지는 미정입니다')
        if (generation.offer is None or generation.offer.status != 'pending'
                or generation.offer.basis_draft != draft or generation.preview is not None
                or generation.condition_change_pending or generation.pending_condition_fields):
            raise ValueError('동일 조건의 pending 권유와 생성 전 상태가 필요합니다')
        if not state.payload.history or state.payload.history[-1].role != 'assistant':
            raise ValueError('권유를 설명한 마지막 답변이 필요합니다')
        offer_results = [message for message in state.payload.history
                         if message.role == 'tool' and message.name == 'update_generation_offer']
        try:
            stored_offer = json.loads(offer_results[-1].content)['offer']
        except (IndexError, KeyError, TypeError, ValueError) as error:
            raise ValueError('권유 Tool의 결과 JSON이 필요합니다') from error
        if stored_offer != generation.offer.model_dump(mode='json'):
            raise ValueError('이력의 권유와 저장 상태의 권유가 다릅니다')
        # 공개 JSON 검사 외에 SDK 메시지로도 복원 가능한 상태인지 확인한다.
        restore_history(state)
        return self


def load_fixture(path: Path = DEFAULT_FIXTURE) -> LatencyFixture:
    return LatencyFixture.model_validate_json(path.read_text())


def make_request(fixture: LatencyFixture, case: LatencyCase, attempt_id: str):
    # 지난 반복의 next_state가 아닌 고정 JSON을 복원한다. 중첩 dict도 공유하지 않는다.
    state = parse_resume_state(fixture.resume_state.model_dump_json())
    common = dict(request_id=attempt_id, club_id=state.club_id, event_id=state.event_id,
                  conversation_id=state.conversation_id, base_revision=fixture.base_revision,
                  draft=state.payload.basis_draft, resume_state=state,
                  reference_date=fixture.reference_date, timezone=fixture.timezone)
    if case.id == 'G2':
        return PlanningPreviewRequest(**common)
    return PlanningChatRequest(**common, message=dict(id=f'{attempt_id}-user', content=case.message))


def request_hashes(request) -> dict:
    # 집계에서는 저장 당시의 JSON을 그대로 해시한다. 현재 타입의 기본값을 새로 넣지 않는다.
    actual = request if isinstance(request, dict) else request.model_dump(mode='json')
    normalized = {**actual, 'request_id': '<request-id>'}
    if 'message' in normalized:
        normalized['message'] = {**normalized['message'], 'id': '<message-id>'}
    return dict(request_sha256=digest(actual), normalized_input_sha256=digest(normalized))


def schedule(fixture: LatencyFixture, rounds: int, warmup: bool = True) -> list[tuple[str, int, LatencyCase]]:
    if type(rounds) is not int or rounds < 1:
        raise ValueError('반복 라운드는 1 이상 정수여야 합니다')
    by_id = {case.id: case for case in fixture.cases}
    plan = [('warmup', 0, by_id[case_id]) for case_id in CASE_IDS] if warmup else []
    for number in range(1, rounds + 1):
        order = CASE_IDS if number % 2 else tuple(reversed(CASE_IDS))
        plan.extend(('measurement', number, by_id[case_id]) for case_id in order)
    return plan
