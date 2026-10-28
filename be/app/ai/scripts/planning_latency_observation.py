"""#196: 측정 프로세스에서만 기존 함수를 감싼다. 모델 설정과 공개 계약은 바꾸지 않는다."""

import asyncio
import math
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from itertools import count
from threading import Lock
from unittest.mock import patch

from pydantic import ValidationError

from app.ai.errors import (
    AIConfigError, AIInvalidResponseError, AIOutputLimitError, AIRetryableError,
    AITimeoutError, PlanningStateError,
)

STAGES = ('agent_model', 'generation', 'compose_plan', 'generation_model', 'validate_plan')
MODEL_STAGES = ('agent_model', 'generation_model')
OBSERVATION_SCOPE = 'planning_function_wrappers_v1'
CURRENT_TRACE = ContextVar('planning_latency_trace', default=None)
PARENT_SPAN = ContextVar('planning_latency_parent', default=None)
INSTALL_LOCK = Lock()

PARENTS = dict(agent_model=None, generation=None, compose_plan='generation',
               generation_model='compose_plan', validate_plan='generation')


def error_category(error, stage=None) -> str:
    for kind, name in ((AIOutputLimitError, 'output_limit'), (AITimeoutError, 'timeout'),
                       (AIInvalidResponseError, 'invalid_plan' if stage == 'validate_plan' else 'invalid_output'),
                       (PlanningStateError, 'invalid_state'), (AIConfigError, 'configuration'),
                       (AIRetryableError, 'retryable'), (ValidationError, 'invalid_result')):
        if isinstance(error, kind):
            return name
    return 'unexpected_error'


class RequestTrace:
    def __init__(self, clock):
        self.clock = clock
        self.origin_ns = None
        self.spans = []
        self.ids = count(1)
        self.error_origins = []  # 예외 객체는 연결에만 쓰고 JSON에는 복사하지 않는다.

    @contextmanager
    def span(self, stage, **details):
        start = self.clock()
        item = dict(id=next(self.ids), parent_id=PARENT_SPAN.get(), stage=stage,
                    start_ms=(start - self.origin_ns) / 1_000_000, end_ms=None, duration_ms=None,
                    outcome='running', failure_code=None, error_type=None, **details)
        self.spans.append(item)
        token = PARENT_SPAN.set(item['id'])
        try:
            yield item
            item['outcome'] = 'ok'
        except BaseException as error:
            item['outcome'] = 'interrupted' if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)) else 'error'
            item['error_type'] = type(error).__name__
            item['failure_code'] = 'interrupted' if item['outcome'] == 'interrupted' else error_category(error, stage)
            if not any(original is error for original, _ in self.error_origins):
                self.error_origins.append((error, item['id']))
            raise
        finally:
            end = self.clock()
            item['end_ms'] = (end - self.origin_ns) / 1_000_000
            item['duration_ms'] = (end - start) / 1_000_000
            PARENT_SPAN.reset(token)

    def origin_for(self, error):
        for original, span_id in self.error_origins:
            if original is error:
                return next(item for item in self.spans if item['id'] == span_id)
        return None

    def below(self, item, parent_id):
        by_id = {span['id']: span for span in self.spans}
        current = item['parent_id']
        while current is not None:
            if current == parent_id:
                return True
            current = by_id[current]['parent_id']
        return False

    def returned_generation(self, item, result):
        if result.status == 'generated':
            return
        if result.status == 'needs_clarification':
            item.update(outcome='not_generated', failure_code='needs_clarification')
            return
        origin = next((child for child in reversed(self.spans)
                       if child['outcome'] == 'error' and self.below(child, item['id'])), None)
        item.update(outcome='error', failure_code=origin['failure_code'] if origin else 'generation_failed',
                    error_type=origin['error_type'] if origin else None,
                    failure_origin_id=origin['id'] if origin else item['id'])

    def generation_failure(self):
        latest = next((item for item in reversed(self.spans) if item['stage'] == 'generation'), None)
        if latest is None or latest['outcome'] != 'error':
            return None
        span_id = latest.get('failure_origin_id', latest['id'])
        return next(item for item in self.spans if item['id'] == span_id)

    def snapshot(self, request_ms=None):
        # 다른 task나 결과 검사에서 이 기록을 계속 바꾸지 못하도록 복사한다.
        spans = deepcopy(self.spans)
        if request_ms is not None:
            spans = [item for item in spans if item['start_ms'] <= request_ms]
            for item in spans:
                if item['end_ms'] is None or item['end_ms'] > request_ms:
                    # 취소 후에도 executor의 동기 함수가 뒤늦게 끝날 수 있다.
                    # 요청 종료 시점에는 미완료였으므로 그 이후 시간을 섞지 않는다.
                    item.update(outcome='running', end_ms=None, duration_ms=None, failure_code=None, error_type=None)
                    item.pop('failure_origin_id', None)
        return dict(version=1, scope=OBSERVATION_SCOPE, spans=spans,
                    complete=all(item['outcome'] != 'running' for item in spans),
                    model_call_attempts={stage: sum(item['stage'] == stage for item in spans)
                                         for stage in MODEL_STAGES})


@contextmanager
def capture_request(clock):
    trace = RequestTrace(clock)
    trace_token = CURRENT_TRACE.set(trace)
    parent_token = PARENT_SPAN.set(None)
    try:
        yield trace
    finally:
        PARENT_SPAN.reset(parent_token)
        CURRENT_TRACE.reset(trace_token)


def model_input(messages):
    # 메시지 본문이나 Tool 인자를 저장하지 않는다. text 길이는 토큰 수와 다르다.
    return dict(input_message_count=len(messages), message_text_chars=sum(len(message.text) for message in messages))


def wrap_async(function, stage):
    @wraps(function)
    async def observed(*args, **kwargs):
        trace = CURRENT_TRACE.get()
        if trace is None:
            return await function(*args, **kwargs)
        details = model_input(args[0]) if stage in MODEL_STAGES else {}
        with trace.span(stage, **details) as item:
            result = await function(*args, **kwargs)
        # 반환 직후 시간을 확정한 뒤 결과 상태만 연결한다.
        if stage == 'generation':
            trace.returned_generation(item, result)
        return result
    return observed


@contextmanager
def install_observers():
    """한 CLI 세션에만 설치한다. 요청 밖의 호출은 그대로 통과시키고 종료 시 전부 복원한다."""
    from app.ai.features.planning import public_workflow
    from app.ai.features.planning.agent import graph as agent_graph
    from app.ai.features.planning.generation import graph as generation_graph

    if not INSTALL_LOCK.acquire(blocking=False):
        raise RuntimeError('같은 프로세스의 동시 관측 세션은 지원하지 않습니다')
    original_compose, original_validate = generation_graph.compose_plan, generation_graph.validate_plan

    @wraps(original_compose)
    async def compose(state, *, invoke):
        trace = CURRENT_TRACE.get()
        if trace is None:
            return await original_compose(state, invoke=invoke)
        with trace.span('compose_plan'):
            # 기본 인자로 이미 묶인 invoke도 여기서 감싸 누락 없이 시도를 센다.
            return await original_compose(state, invoke=wrap_async(invoke, 'generation_model'))

    @wraps(original_validate)
    def validate(state):
        trace = CURRENT_TRACE.get()
        if trace is None:
            return original_validate(state)
        with trace.span('validate_plan'):
            return original_validate(state)

    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(agent_graph, 'call_agent_model', wrap_async(agent_graph.call_agent_model, 'agent_model')))
            stack.enter_context(patch.object(public_workflow, 'run_plan_generation',
                                             wrap_async(public_workflow.run_plan_generation, 'generation')))
            stack.enter_context(patch.object(generation_graph, 'compose_plan', compose))
            stack.enter_context(patch.object(generation_graph, 'validate_plan', validate))
            yield
    finally:
        INSTALL_LOCK.release()


def validate_observation(observation, request_ms, *, allow_pending=False):
    """기록을 읽을 때 호출 수와 포함 관계를 확인한다. 잘못된 시간을 통계에 섞지 않는다."""
    def require(condition):
        if not condition:
            raise ValueError('구간 관측 기록이 유효하지 않습니다')

    def duration(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0

    require(isinstance(observation, dict) and type(observation.get('version')) is int
            and observation['version'] == 1 and observation.get('scope') == OBSERVATION_SCOPE)
    spans = observation.get('spans')
    require(isinstance(spans, list))
    by_id, siblings = {}, {}
    for item in spans:
        require(isinstance(item, dict) and type(item.get('id')) is int and item['id'] > 0 and item['id'] not in by_id)
        require(item.get('stage') in STAGES and item.get('outcome') in ('ok', 'error', 'interrupted', 'not_generated', 'running'))
        parent_id = item.get('parent_id')
        require(parent_id is None or type(parent_id) is int and parent_id in by_id)
        parent = by_id.get(parent_id)
        require((parent['stage'] if parent else None) == PARENTS[item['stage']])
        pending = item['outcome'] == 'running'
        require(duration(item.get('start_ms')) and item['start_ms'] <= request_ms + 1e-6)
        if pending:
            require(allow_pending and item.get('end_ms') is None and item.get('duration_ms') is None)
        else:
            require(all(duration(item.get(key)) for key in ('end_ms', 'duration_ms')))
            require(item['start_ms'] <= item['end_ms'] <= request_ms + 1e-6)
            require(math.isclose(item['duration_ms'], item['end_ms'] - item['start_ms'], rel_tol=1e-9, abs_tol=1e-6))
        if parent:
            require(parent['start_ms'] <= item['start_ms'] + 1e-6)
            if parent['end_ms'] is not None:
                require((item['start_ms'] if pending else item['end_ms']) <= parent['end_ms'] + 1e-6)
        previous = siblings.get(parent_id)
        if previous:
            require(previous['end_ms'] is not None and previous['end_ms'] <= item['start_ms'] + 1e-6)
        siblings[parent_id] = item
        if item['outcome'] in ('ok', 'running'):
            require(item.get('failure_code') is None and item.get('error_type') is None)
        else:
            require(isinstance(item.get('failure_code'), str) and item['failure_code'])
            require(item.get('error_type') is None or isinstance(item['error_type'], str))
        if item['outcome'] == 'not_generated':
            require(item['stage'] == 'generation' and item['failure_code'] == 'needs_clarification')
        if item['stage'] in MODEL_STAGES:
            require(all(type(item.get(key)) is int and item[key] >= 0 for key in ('input_message_count', 'message_text_chars')))
        by_id[item['id']] = item
    for item in spans:
        if 'failure_origin_id' in item:
            origin_id = item['failure_origin_id']
            require(type(origin_id) is int and origin_id in by_id and item['stage'] == 'generation')
            origin = by_id[origin_id]
            current = origin
            while current['parent_id'] is not None and current['id'] != item['id']:
                current = by_id[current['parent_id']]
            require(current['id'] == item['id'] and origin['outcome'] == 'error'
                    and origin['failure_code'] == item['failure_code'])
    expected = {stage: sum(item['stage'] == stage for item in spans) for stage in MODEL_STAGES}
    counts = observation.get('model_call_attempts')
    require(isinstance(counts, dict) and counts == expected and all(type(value) is int for value in counts.values()))
    require(type(observation.get('complete')) is bool
            and observation['complete'] == all(item['outcome'] != 'running' for item in spans))
