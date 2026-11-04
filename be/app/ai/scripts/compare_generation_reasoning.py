"""생성 모델 설정 두 가지를 같은 실행 안에서 번갈아 잰다. --compare로 무엇을 비교할지 고른다.

  reasoning   #264 추론 깊이 default / low. 출력 형식은 현재 코드(v2)
  step-codes  #276 출력 형식 v1(단계 코드 17개, CANCEL_* 포함) / v2(카탈로그 13개). 추론 깊이는 둘 다 low

기본 사례는 G2(버튼 생성)다. 대화 모델을 부르지 않고 생성 모델을 1번만 불러, 추론 깊이의 효과만 보이게 하려는 것이다.
--case G1(채팅 "응, 만들어줘.")은 같은 설정이 채팅 경로 전체 시간에 주는 효과를 확인할 때 쓴다(대화 모델 호출 포함).
생성 지시문, 출력 한도, 스트리밍, 모델은 같고 비교하는 값 하나만 다르다. 한 세션의 순서는 아래와 같다(reasoning 예).
  준비 실행   default·low 한 번씩(집계 제외)
  본측정     홀수 라운드 default → low, 짝수 라운드 low → default
성공 판정·구간 시간·토큰 기록은 #263 측정기(measure_attempt)를, 검증 거절 규칙은 #239 수집기를 그대로 쓴다.

생성 모델 응답에 카탈로그 밖 단계 코드(CANCEL_* 등)가 있었는지도 요청마다 남긴다(코드 이름만, 본문은 저장하지 않음).
v2에서 모델이 CANCEL_*를 쓰면 계획 검사 전에 출력 형식 실패(invalid_output)가 되어 검증 원본이 남지 않기 때문이다.

  .venv/bin/python -m app.ai.scripts.compare_generation_reasoning --output-dir <작업 트리 밖 폴더> --session-id s1
  .venv/bin/python -m app.ai.scripts.compare_generation_reasoning --compare step-codes --case G1 --output-dir <폴더> --session-id s1
"""

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from pathlib import Path
from statistics import median
from unittest.mock import patch

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.tracers.context import register_configure_hook

from app.ai import chat_planning, generate_planning_preview
from app.ai.config import AISettings
from app.ai.features.planning.generation import graph as generation_graph, model as generation_model
from app.ai.planning_catalog import PLANNING_STEP_NAMES
from app.ai.scripts import generation_output_v1
from app.ai.scripts.measure_planning_latency import append_event, execution_metadata, measure_attempt, now, write_manifest
from app.ai.scripts.planning_latency_inputs import DEFAULT_FIXTURE, json_text, load_fixture, make_request
from app.ai.scripts.planning_latency_observation import CURRENT_TRACE, PARENT_SPAN, install_observers
from app.ai.scripts.planning_latency_summary import summarize_group
from app.ai.scripts.planning_validation_diagnostics import capture_validation_failures, validator_source, write_snapshot

CASE_IDS = ('G2', 'G1')
CALLS = dict(G1=chat_planning, G2=generate_planning_preview)
LOW = {'effort': 'low'}
V1_VERSION = 'planning-generation-v1'
# 변형마다 생성 모델에 보낼 reasoning과 출력 형식. composition=None은 현재 코드(v2)의 형식이다.
# reasoning=None은 값을 보내지 않는다(공급자 기본값). 코드의 기본 설정이 바뀌어도 이 비교의 기준은 같다.
COMPARISONS = {
    'reasoning': dict(
        purpose='#264 생성 모델 추론 깊이 default/low 번갈아 비교',
        scope='생성 지시문·출력 형식·출력 한도·스트리밍·모델은 같고 reasoning만 다르다',
        variants=dict(default=dict(reasoning=None, composition=None,
                                   description='reasoning 미지정(공급자 기본값, 값 미확인)'),
                      low=dict(reasoning=LOW, composition=None, description='reasoning={"effort": "low"}'))),
    'step-codes': dict(
        purpose='#276 생성 출력 형식 v1/v2 번갈아 비교',
        scope='생성 지시문·reasoning(low)·출력 한도·스트리밍·모델은 같고 출력 형식의 단계 코드 허용값만 다르다',
        variants=dict(v1=dict(reasoning=LOW, composition=generation_output_v1.PlanComposition,
                              description='출력 형식 v1: 단계 코드 17개(카탈로그 13 + CANCEL_* 4), reasoning low'),
                      v2=dict(reasoning=LOW, composition=None,
                              description='출력 형식 v2: 카탈로그 13개(현재 코드), reasoning low'))),
}
VARIANTS = COMPARISONS['reasoning']['variants']
BUILD_PLAN_MODEL = generation_model.build_plan_model
CODE_PATTERN = re.compile(r'"code"\s*:\s*"([A-Z_]+)"')


def variant_builder(name, comparison='reasoning'):
    """build_plan_model 대신 끼울 함수. 출력 한도·스트리밍은 원래 함수가 정하고 reasoning만 덮어쓴다."""
    overrides = dict(reasoning=COMPARISONS[comparison]['variants'][name]['reasoning'])
    def build(settings=None, **extra):
        return BUILD_PLAN_MODEL(settings, **{**overrides, **extra})
    return build


@contextmanager
def variant_patches(name, comparison='reasoning'):
    """이 요청 동안만 생성 모델 설정과 출력 형식을 바꾼다. 끝나면 현재 코드로 돌아간다."""
    variant = COMPARISONS[comparison]['variants'][name]
    with ExitStack() as stack:
        stack.enter_context(patch.object(generation_model, 'build_plan_model', variant_builder(name, comparison)))
        if variant['composition'] is not None:
            # compose_plan은 모듈의 PlanComposition을 모델 요청 형식과 응답 확인에 함께 쓴다.
            # 버전도 바꿔 두어야 검증 원본(generation_prompt_version)에 v1로 남는다.
            stack.enter_context(patch.object(generation_graph, 'PlanComposition', variant['composition']))
            stack.enter_context(patch.object(generation_graph, 'PROMPT_VERSION', V1_VERSION))
        yield


# 요청 하나 동안 생성 모델 응답에서 본 카탈로그 밖 단계 코드. 값이 있을 때만 콜백이 붙는다.
OUTSIDE_CODES = ContextVar('generation_outside_catalog_codes', default=None)


class OutsideCodeRecorder(AsyncCallbackHandler):
    """생성 모델 응답 원문에서 "code" 값만 뽑아 카탈로그 밖 코드를 기록한다. 원문은 저장하지 않는다.

    v2에서 CANCEL_*가 오면 형식 확인에서 실패해 계획 초안이 남지 않으므로 응답이 끝나는 시점에 본다.
    """
    run_inline = True

    def __init__(self, found):
        self.found = found

    async def on_llm_end(self, response, **kwargs):
        trace, span_id = CURRENT_TRACE.get(), PARENT_SPAN.get()
        span = next((item for item in trace.spans if item['id'] == span_id), None) if trace and span_id else None
        if span is None or span['stage'] != 'generation_model':
            return
        try:
            text = response.generations[0][0].message.text
        except (AttributeError, IndexError):
            return
        for code in CODE_PATTERN.findall(text or ''):
            if code not in PLANNING_STEP_NAMES and code not in self.found:
                self.found.append(code)


register_configure_hook(OUTSIDE_CODES, inheritable=True)


def schedule(rounds, names=tuple(VARIANTS)):
    """(phase, round, variant) 목록. 순서 효과를 줄이려고 라운드마다 변형 순서를 뒤집는다."""
    plan = [('warmup', 0, name) for name in names]
    for number in range(1, rounds + 1):
        plan += [('measurement', number, name) for name in (names if number % 2 else reversed(names))]
    return plan


def generation_calls(row):
    return [span for span in row.get('observation', {}).get('spans', []) if span['stage'] == 'generation_model']


def summarize(rows, names=tuple(VARIANTS)):
    """변형별 #263 집계에 채택 기준(통과 수·생성 호출 p50·단계 수)과 검증 거절 규칙을 더한다."""
    result = {}
    for name in names:
        selected = [row for row in rows if row['phase'] == 'measurement' and row['variant'] == name]
        succeeded = [row for row in selected if row['outcome'] == 'success']
        steps = [row['output']['step_count'] for row in succeeded]
        result[name] = dict(
            latency=summarize_group(selected, selected, selected),
            success_step_count=dict(n=len(steps), median=median(steps) if steps else None,
                                    min=min(steps, default=None), max=max(steps, default=None)),
            violations=dict(Counter(item['rule'] for row in selected for item in row.get('violations', []))),
            failures=dict(Counter(row['failure']['category'] for row in selected if row.get('failure'))),
            # 응답에 카탈로그 밖 코드가 있었던 요청 수와 그 요청의 결과(#276 기준 ①).
            outside_catalog=dict(
                requests=sum(1 for row in selected if row.get('outside_catalog_codes')),
                outcomes=dict(Counter((row['failure']['category'] if row.get('failure') else row['outcome'])
                                      for row in selected if row.get('outside_catalog_codes'))),
                codes=dict(Counter(code for row in selected for code in row.get('outside_catalog_codes', [])))),
        )
    return result


async def run_session(output_dir: Path, *, session_id, case_id='G2', comparison='reasoning', rounds=10, interval=1.0,
                      settings=None, sleep=asyncio.sleep):
    fixture = load_fixture()
    if settings is None:
        settings = AISettings()
        settings.require_api()
    case = next(item for item in fixture.cases if item.id == case_id)
    variants = COMPARISONS[comparison]['variants']
    names = tuple(variants)
    plan = schedule(rounds, names)
    source = validator_source()
    report = dict(
        report_version=1, session_id=session_id, status='running', started_at=now(),
        comparison=comparison, purpose=COMPARISONS[comparison]['purpose'],
        variants={name: value['description'] for name, value in variants.items()},
        scope=f"{COMPARISONS[comparison]['scope']}. 사례는 {case_id}",
        generation_prompt_versions={name: V1_VERSION if value['composition'] is not None else generation_graph.PROMPT_VERSION
                                    for name, value in variants.items()},
        fixture_sha256=hashlib.sha256(DEFAULT_FIXTURE.read_bytes()).hexdigest(),
        generation_prompt_version=generation_graph.PROMPT_VERSION,
        generation_prompt_sha256=hashlib.sha256(generation_graph.PROMPT.encode()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        profile=dict(rounds=rounds, interval_seconds=interval, concurrency=1, case_id=case_id),
        environment=execution_metadata('real_model', settings),
        validator_source=source.model_dump(), planned=len(plan), finished=0,
    )
    # 공통 메타정보의 reasoning은 현재 코드의 값이다. 이 실행은 요청마다 바꾸므로 변형별 값으로 적는다.
    report['environment']['model_options']['reasoning'] = {name: value['reasoning'] for name, value in variants.items()}
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / 'validation').mkdir()
    write_manifest(output_dir, report)
    rows = []
    try:
        with (output_dir / 'attempts.jsonl').open('x') as stream:
            for index, (phase, number, variant) in enumerate(plan):
                attempt_id = f'{session_id}-{phase}-{number:03d}-{case_id}-{variant}'
                identity = dict(attempt_id=attempt_id, phase=phase, round=number, case_id=case_id, variant=variant)
                request = make_request(fixture, case, attempt_id)
                request_data = request.model_dump(mode='json')
                append_event(stream, dict(event='started', started_at=now(), **identity, request=request_data,
                                          request_sha256=hashlib.sha256(json_text(request_data).encode()).hexdigest()))
                # 수집기가 바깥, 관측기가 안쪽이어야 검증 거절이 열린 validate_plan 구간 안에서 잡힌다(#239와 같은 순서).
                # 이 요청 동안만 생성 모델 설정을 바꾼다. 끝나면 현재 코드로 돌아간다.
                outside = []
                token = OUTSIDE_CODES.set(OutsideCodeRecorder(outside))
                try:
                    with capture_validation_failures(request, run_id=session_id, model=settings.model, source=source) as capture, \
                            install_observers(), variant_patches(variant, comparison):
                        measured, interrupted = await measure_attempt(case, request, CALLS[case_id])
                finally:
                    OUTSIDE_CODES.reset(token)
                if interrupted:
                    raise asyncio.CancelledError
                violations = []
                for number_in_request, snapshot in enumerate(capture.snapshots, 1):
                    filename = f'{attempt_id}-{number_in_request}.json'
                    write_snapshot(output_dir / 'validation' / filename, snapshot)
                    violations.append(dict(rule=snapshot.violation.rule, path=snapshot.violation.path,
                                           step_code=snapshot.violation.step_code, file=f'validation/{filename}'))
                row = dict(event='finished', finished_at=now(), **identity, **measured,
                           violations=violations, capture_errors=capture.errors, outside_catalog_codes=outside)
                append_event(stream, row)
                rows.append(row)
                report['finished'] = len(rows)
                write_manifest(output_dir, report)
                usage = [span.get('usage') or {} for span in generation_calls(row)]
                print(json.dumps(dict(**identity, outcome=row['outcome'], seconds=round(row['ai_request_ms'] / 1000, 2),
                                      output_tokens=[item.get('output_tokens') for item in usage],
                                      reasoning_tokens=[item.get('reasoning_tokens') for item in usage],
                                      violations=[item['rule'] for item in violations],
                                      outside_catalog_codes=outside), ensure_ascii=False), flush=True)
                if index + 1 < len(plan):
                    await sleep(interval)
        report['status'] = 'completed'
    except (asyncio.CancelledError, KeyboardInterrupt):
        report['status'] = 'interrupted'
        raise
    except BaseException:
        report['status'] = 'runner_failed'
        raise
    finally:
        report.update(finished_at=now(), summary=summarize(rows, names))
        write_manifest(output_dir, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--case', choices=CASE_IDS, default='G2')
    parser.add_argument('--compare', choices=tuple(COMPARISONS), default='reasoning')
    parser.add_argument('--rounds', type=int, default=10)
    parser.add_argument('--interval-seconds', type=float, default=1.0)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('rounds는 1 이상이어야 합니다')
    try:
        report = asyncio.run(run_session(args.output_dir, session_id=args.session_id, case_id=args.case,
                                         comparison=args.compare, rounds=args.rounds, interval=args.interval_seconds))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print('측정을 중단했습니다. 기록과 세션 상태를 확인해 주세요.')
        return 130
    except Exception as error:
        # 예외 원문이나 공급자 응답을 콘솔에 노출하지 않는다.
        print(f'측정 실행 실패: {type(error).__name__}')
        return 1
    print(json.dumps(dict(status=report['status'], finished=report['finished']), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
