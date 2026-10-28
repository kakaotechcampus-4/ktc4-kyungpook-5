"""#196: 검증된 요청 기록을 집계한다. 준비 실행과 본 측정은 호출자가 따로 넘긴다."""

import math
from collections import defaultdict

from app.ai.scripts.planning_latency_observation import MODEL_STAGES, STAGES


def distribution(values) -> dict:
    """NumPy linear/R7과 같은 규칙. 비어 있는 표본은 0ms로 만들지 않는다."""
    samples = list(values)
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError('지연 표본은 0 이상 유한한 숫자여야 합니다')
    samples.sort()

    def percentile(fraction):
        position = (len(samples) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        return samples[lower] + (samples[upper] - samples[lower]) * (position - lower)

    if not samples:
        return dict(n=0, p50_ms=None, p95_ms=None, mean_ms=None, max_ms=None)
    return dict(n=len(samples), p50_ms=percentile(.5), p95_ms=percentile(.95),
                mean_ms=math.fsum(value / len(samples) for value in samples), max_ms=samples[-1])


def summarize_group(planned, started, finished) -> dict:
    successful = [item for item in finished if item['outcome'] == 'success']
    failed = [item for item in finished if item['outcome'] == 'failed']
    interrupted = [item for item in finished if item['outcome'] == 'interrupted']
    pending = len(started) - len(finished)
    not_started = len(planned) - len(started)
    failures = defaultdict(list)
    for item in failed:
        failures[item['failure']['category']].append(item['ai_request_ms'])
    return dict(
        counts=dict(planned=len(planned), started=len(started), finished=len(finished),
                    completed=len(successful) + len(failed), success=len(successful), failed=len(failed),
                    interrupted=len(interrupted), pending=pending, not_started=not_started),
        # 성공만으로 분모를 만들지 않는다. 중단과 종료 대기도 시작한 요청에 포함한다.
        success_rate=len(successful) / len(started) if started else None,
        provisional=bool(pending or interrupted or not_started),
        success_ms=distribution(item['ai_request_ms'] for item in successful),
        failure_ms=distribution(item['ai_request_ms'] for item in failed),
        completed_ms=distribution(item['ai_request_ms'] for item in successful + failed),
        interrupted_wait_ms=distribution(item['ai_request_ms'] for item in interrupted),
        failures_by_category={category: distribution(values) for category, values in sorted(failures.items())},
        observation=summarize_observations(finished),
    )


def summarize_observations(finished):
    observed = [item for item in finished if 'observation' in item]
    if not observed:
        return None  # 예전 기록을 0회/0ms로 관측한 것처럼 처리하지 않는다.
    spans = [span for item in observed for span in item['observation']['spans']]
    by_stage = {}
    for stage in STAGES:
        selected = [span for span in spans if span['stage'] == stage]
        errors = [span for span in selected if span['outcome'] == 'error']
        interrupted = [span for span in selected if span['outcome'] == 'interrupted']
        pending = [span for span in selected if span['outcome'] == 'running']
        codes = defaultdict(int)
        for span in errors:
            codes[span['failure_code']] += 1
        by_stage[stage] = dict(
            calls=len(selected), error_calls=len(errors), interrupted_calls=len(interrupted), pending_calls=len(pending),
            not_generated_calls=sum(span['outcome'] == 'not_generated' for span in selected),
            per_call_ms=distribution(span['duration_ms'] for span in selected if span['outcome'] not in ('interrupted', 'running')),
            ok_call_ms=distribution(span['duration_ms'] for span in selected if span['outcome'] == 'ok'),
            error_call_ms=distribution(span['duration_ms'] for span in errors),
            interrupted_wait_ms=distribution(span['duration_ms'] for span in interrupted),
            # 같은 구간의 여러 호출만 합한다. 부모와 자식인 다른 구간끼리는 더하지 않는다.
            per_completed_request_total_ms=distribution(
                sum(span['duration_ms'] for span in item['observation']['spans'] if span['stage'] == stage)
                for item in observed if item['outcome'] != 'interrupted' and not any(
                    span['stage'] == stage and span['outcome'] == 'running' for span in item['observation']['spans'])),
            error_codes=dict(codes),
        )
    return dict(observed_requests=len(observed), unobserved_requests=len(finished) - len(observed),
                complete=all(item['observation']['complete'] for item in observed),
                model_call_attempts={stage: sum(item['observation']['model_call_attempts'][stage] for item in observed)
                                     for stage in MODEL_STAGES}, by_stage=by_stage)
