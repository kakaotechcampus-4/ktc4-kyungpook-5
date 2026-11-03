"""#239 합성 진단의 실패 자료 수집과 모델 없는 재검사. 제품의 저장/재시도는 건드리지 않는다."""

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import subprocess
from threading import Lock
from typing import Literal, Self
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ai import PlanningChatRequest
from app.ai.features.planning.agent.nodes import PROMPT_VERSION as AGENT_PROMPT_VERSION
from app.ai.features.planning.generation import graph
from app.ai.features.planning.generation.schemas import PlanComposition, PlanGenerationInput
from app.ai.features.planning.generation.validation import PlanValidationError, PlanValidationViolation
from app.ai.scripts.measure_planning_latency import now
from app.ai.scripts.planning_latency_inputs import AI_DIR, digest
from app.ai.scripts.planning_latency_observation import CURRENT_TRACE, PARENT_SPAN


VALIDATOR_FILES = (
    'features/planning/generation/graph.py', 'features/planning/generation/validation.py',
    'features/planning/generation/schemas.py', 'features/planning/generation/catalog.py',
    'contracts.py', 'planning_catalog.py', 'errors.py',
)
CAPTURE_LOCK = Lock()


class ValidatorSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    commit: str
    sha256: dict[str, str]


def validator_source() -> ValidatorSource:
    return ValidatorSource(commit=subprocess.check_output(['git', '-C', str(AI_DIR), 'rev-parse', 'HEAD'], text=True).strip(),
        sha256={name: hashlib.sha256((AI_DIR / name).read_bytes()).hexdigest() for name in VALIDATOR_FILES})


class ValidationSnapshot(BaseModel):
    """진단 파일의 버전이다. 공개 대화 상태의 schema_version과는 별개다."""
    model_config = ConfigDict(frozen=True, extra='forbid')
    artifact_version: Literal[1] = 1
    scope: Literal['synthetic_planning_validation'] = 'synthetic_planning_validation'
    run_id: str
    request_id: str
    route: Literal['chat', 'button']
    generation_attempt: int = Field(ge=1)
    generation_span_id: int = Field(ge=1)
    validation_span_id: int = Field(ge=1)
    captured_at: str
    model: str | None
    agent_prompt_version: str
    generation_prompt_version: str
    source: ValidatorSource
    input: PlanGenerationInput
    composition: PlanComposition
    violation: PlanValidationViolation
    input_sha256: str
    composition_sha256: str

    @model_validator(mode='after')
    def check_saved_material(self) -> Self:
        if self.input.messages or self.input.trigger.source != self.route:
            raise ValueError('재검사에는 대화 본문을 넣지 않으며 요청 출처가 일치해야 합니다')
        if self.input_sha256 != digest(self.input.model_dump(mode='json', exclude={'messages'})):
            raise ValueError('재검사 입력 해시가 맞지 않습니다')
        if self.composition_sha256 != digest(self.composition.model_dump(mode='json')):
            raise ValueError('초안 해시가 맞지 않습니다')
        return self


@dataclass
class ValidationCapture:
    snapshots: list[ValidationSnapshot] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@contextmanager
def capture_validation_failures(request, *, run_id, model, source=None):
    """이 context 안에 install_observers를 설치하고 공개 요청 한 건을 순차 실행한다."""
    if not CAPTURE_LOCK.acquire(blocking=False):
        raise RuntimeError('검증 자료 수집은 동시에 설치할 수 없습니다')
    capture = ValidationCapture()
    original = graph.validate_plan
    try:
        source = source or validator_source()

        def validate(state):
            try:
                return original(state)
            except PlanValidationError as error:
                trace = CURRENT_TRACE.get()
                span_id = PARENT_SPAN.get()
                validations = [s for s in trace.spans if s['id'] == span_id and s['stage'] == 'validate_plan'] if trace else []
                roots = [s for s in trace.spans if s['stage'] == 'generation'] if trace else []
                if not validations or not roots:
                    capture.errors.append('missing_observation_context')
                else:
                    # 대화/SDK 응답은 제외한다. 검증이 실제로 받은 조건과 구조화 초안만 복사한다.
                    try:
                        input_data = state['request'].model_dump(mode='json', exclude={'messages'})
                        composition_data = state['composition'].model_dump(mode='json')
                        capture.snapshots.append(ValidationSnapshot(
                            run_id=run_id, request_id=request.request_id,
                            route='chat' if isinstance(request, PlanningChatRequest) else 'button',
                            generation_attempt=len(roots), generation_span_id=validations[0]['parent_id'],
                            validation_span_id=span_id, captured_at=now(), model=model,
                            agent_prompt_version=AGENT_PROMPT_VERSION, generation_prompt_version=graph.PROMPT_VERSION,
                            source=source, input=PlanGenerationInput.model_validate(input_data),
                            composition=PlanComposition.model_validate(composition_data),
                            violation=error.violation.model_copy(deep=True),
                            input_sha256=digest(input_data), composition_sha256=digest(composition_data)))
                    except Exception as capture_error:
                        # 수집 오류는 진단 세션을 실패시키지만 원래 P1 실패를 다른 예외로 바꾸지 않는다.
                        capture.errors.append(type(capture_error).__name__)
                # 같은 예외를 다시 올려 기존 Graph의 실패 처리와 Agent 재시도를 유지한다.
                raise

        with patch.object(graph, 'validate_plan', validate):
            yield capture
    finally:
        CAPTURE_LOCK.release()


def write_snapshot(path: Path, snapshot: ValidationSnapshot):
    data = snapshot.model_dump(mode='json', exclude={'input': {'messages'}})
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def replay_snapshot(snapshot: ValidationSnapshot) -> dict:
    """모델/설정을 부르지 않고 저장한 동일 입력과 초안을 검사한다."""
    source = validator_source()
    result = dict(replay_version=1, recorded_source=snapshot.source.model_dump(), current_source=source.model_dump(),
                  same_validator_source=snapshot.source.sha256 == source.sha256,
                  expected_violation=snapshot.violation.model_dump(mode='json'), reproduced=False)
    try:
        graph.validate_plan(dict(request=snapshot.input.model_copy(deep=True),
                                 composition=snapshot.composition.model_copy(deep=True)))
    except PlanValidationError as error:
        result.update(status='rejected', actual_violation=error.violation.model_dump(mode='json'),
                      reproduced=error.violation == snapshot.violation)
    except Exception as error:
        result.update(status='unexpected_error', error_type=type(error).__name__)
    else:
        result.update(status='accepted', actual_violation=None)
    return result
