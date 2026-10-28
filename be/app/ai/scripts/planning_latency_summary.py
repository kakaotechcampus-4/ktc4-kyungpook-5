"""#196: 검증된 요청 기록을 집계한다. 준비 실행과 본 측정은 호출자가 따로 넘긴다."""

import math
from collections import defaultdict


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
    )
