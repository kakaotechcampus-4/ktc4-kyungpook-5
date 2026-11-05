"""#333: 고정 사례 10개로 실제 모델의 운영 Action 본문 초안(draft_action_content)을 재고 결과를 저장한다.

실행(be/에서, 모델 설정이 있는 .env가 있는 곳):
  uv run python -m app.ai.scripts.run_action_draft_eval --out app/ai/docs/operations-evaluation-results/action-draft-2026-11-06
키·base URL·요청 헤더는 읽지도 기록하지도 않는다. 모델 이름, 프롬프트 버전, 커밋, 사례별 본문·검사 결과·시간만 남긴다.

사례마다 자동으로 보는 것:
  check       코드 검사를 첫 호출에서 통과(first), 다시 써서 통과(retry), 두 번 다 걸림(failed), 모델 오류(error)
  placeholder 비어 있는 값을 [ ]로 비웠는지. 공지(NOTICE)에서 장소가 없으면 "장소", 기한이 없으면
              "마감·기한·날짜"가 들어간 자리표시가 있어야 한다. 해당 없는 사례는 null
  forbidden   "발송했", "확정됐" 같은 완료 단정 표현이 없는지
  title       첫 줄이 대괄호로 시작하지 않고, 행사명이 unknowns에 들어가지 않았는지
  emoji       이모지가 2개 이하인지
운영진이 조금만 고쳐 바로 올릴 수 있는지(수동 확인)는 drafts-<label>.md를 읽고 평가 문서에 적는다.
"""
import argparse
import asyncio
import json
import re
import subprocess
import time
from datetime import date
from pathlib import Path

from app.ai import ActionDraftRequest, ActionDraftResult
from app.ai.config import get_settings
from app.ai.features.operations.action_draft import PROMPT_VERSION, draft_attempts

CASES_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eval" / "action_draft_cases.json"

FORBIDDEN = ("발송했", "발송되었", "발송됐", "확정됐", "확정되었", "예약했", "예약을 마쳤", "완료했")
DEADLINE_WORDS = ("마감", "기한", "날짜")
# 공지에 기한이 들어가야 하는 단계. 사전 안내는 기한보다 집결·준비물이 중심이라 기한 자리표시를 보지 않는다.
DEADLINE_STEPS = {"DEMAND_SURVEY", "RECRUIT_NOTICE", "CHECK_RESPONSES", "COLLECT_FEES"}
# 흔한 그림 이모지 범위만 센다. 예: 📢 ✅ 🌸
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def judge(request: ActionDraftRequest, content: str | None) -> dict:
    """본문 하나를 자동 판정한다. 본문이 없으면(실패·오류) 모두 False로 둔다."""
    if content is None:
        return {"placeholder": False, "forbidden_absent": False, "title_not_bracketed": False, "emoji_ok": False}
    unknowns = ActionDraftResult(content=content).unknowns
    is_notice = request.action.type == "NOTICE"

    wants = []
    if is_notice and request.event.location is None:
        wants.append(("장소",))
    if (is_notice and request.step.code in DEADLINE_STEPS
            and request.step.deadline is None and request.action.due_date is None):
        wants.append(DEADLINE_WORDS)
    placeholder = None if not wants else all(
        any(word in name for name in unknowns for word in words) for words in wants)

    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return {
        "placeholder": placeholder,
        "forbidden_absent": not any(word in content for word in FORBIDDEN),
        "title_not_bracketed": not first_line.startswith("[") and request.event.title not in unknowns,
        "emoji_ok": len(_EMOJI.findall(content)) <= 2,
    }


def missing_fields(request: ActionDraftRequest) -> list[str]:
    values = {"location": request.event.location, "end_date": request.event.end_date,
              "step.deadline": request.step.deadline, "action.due_date": request.action.due_date,
              "fee_per_person": request.event.fee_per_person}
    return [name for name, value in values.items() if value is None]


async def run_case(case: dict) -> dict:
    request = ActionDraftRequest.model_validate(case["request"])
    started = time.perf_counter()
    attempts, error = (), None
    try:
        attempts = await draft_attempts(request)
    except Exception as exc:  # 오류 종류만 남기고 메시지는 남기지 않는다.
        error = type(exc).__name__
    elapsed_s = round(time.perf_counter() - started, 2)

    if error:
        check = "error"
    elif not attempts[-1].violations:
        check = "first" if len(attempts) == 1 else "retry"
    else:
        check = "failed"
    final = attempts[-1].content if check in ("first", "retry") else None
    return {
        "id": case["id"], "step": request.step.code.value, "action_type": request.action.type.value,
        "missing": missing_fields(request), "elapsed_s": elapsed_s, "error": error, "check": check,
        "attempts": [{"content": a.content, "violations": list(a.violations)} for a in attempts],
        "unknowns": list(ActionDraftResult(content=final).unknowns) if final else [],
        "checks": judge(request, final),
    }


def _mark(value: bool | None) -> str:
    return "-" if value is None else ("O" if value else "X")


CHECK_LABEL = {"first": "첫 호출 통과", "retry": "다시 써서 통과", "failed": "실패", "error": "오류"}


def summary_table(rows: list[dict]) -> str:
    lines = ["| id | 단계 | 종류 | 미정 | 검사 | 호출 | 자리표시 | 금지 표현 없음 | 제목 줄 | 이모지 ≤2 | 시간(초) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        c = r["checks"]
        lines.append(
            f"| {r['id']} | {r['step']} | {r['action_type']} | {'있음' if 'location' in r['missing'] else '없음'} "
            f"| {CHECK_LABEL[r['check']]}{'(' + r['error'] + ')' if r['error'] else ''} | {len(r['attempts'])} "
            f"| {_mark(c['placeholder'])} | {_mark(c['forbidden_absent'])} | {_mark(c['title_not_bracketed'])} "
            f"| {_mark(c['emoji_ok'])} | {r['elapsed_s']} |")
    return "\n".join(lines)


def drafts_markdown(rows: list[dict], meta: dict) -> str:
    """사람이 읽고 수동 확인하기 위한 본문 모음. 다시 쓴 사례는 앞 본문과 걸린 값도 함께 둔다."""
    out = [f"# 운영 Action 본문 초안 원문 ({meta['label']})", "",
           f"모델 `{meta['model']}`, 프롬프트 `{meta['prompt_version']}`, 커밋 `{meta['commit']}`, 실행일 {meta['run_date']}", ""]
    for r in rows:
        out += [f"## {r['id']} · {r['step']} · {r['action_type']}", "",
                f"검사: {CHECK_LABEL[r['check']]}, 호출 {len(r['attempts'])}번, {r['elapsed_s']}초, "
                f"비어 있던 값: {', '.join(r['missing']) or '없음'}, unknowns: {', '.join(r['unknowns']) or '없음'}", ""]
        for number, attempt in enumerate(r["attempts"], 1):
            out += [f"### 호출 {number}", "", "```text", attempt["content"], "```", ""]
            if attempt["violations"]:
                out += ["걸린 값:", *[f"- {v}" for v in attempt["violations"]], ""]
        if r["error"]:
            out += [f"오류: {r['error']}", ""]
    return "\n".join(out)


def current_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "미확인"


async def main(out: Path, label: str) -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    meta = {"label": label, "model": get_settings().model, "prompt_version": PROMPT_VERSION,
            "commit": current_commit(), "run_date": date.today().isoformat(), "cases": len(cases)}
    # 사례를 하나씩 차례로 부른다. 시간은 사례 하나(다시 쓴 경우 포함)에 걸린 시간이다.
    rows = [await run_case(case) for case in cases]
    out.mkdir(parents=True, exist_ok=True)
    (out / f"results-{label}.json").write_text(
        json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    table = summary_table(rows)
    (out / f"summary-{label}.md").write_text(table + "\n", encoding="utf-8")
    (out / f"drafts-{label}.md").write_text(drafts_markdown(rows, meta) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    print(table)
    counts = {key: sum(r["check"] == key for r in rows) for key in CHECK_LABEL}
    print(", ".join(f"{CHECK_LABEL[k]} {v}" for k, v in counts.items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", default="baseline")
    args = parser.parse_args()
    asyncio.run(main(args.out, args.label))
