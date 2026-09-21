"""ML API 연결과 기능 지원 범위를 실제 호출로 확인한다.

키가 필요해 CI에서 돌리지 않는다. 게이트웨이·모델을 바꿀 때 수동으로 실행한다.

    cd be && uv run python app/ai/scripts/check_ml_api.py

AI_* 는 be/.env 에서 읽는다. 출력은 모두 scrub()을 거쳐 키가 남지 않는다.
"""

from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field

load_dotenv(Path(".env").resolve(), override=True)

from app.ai.config import AISettings  # noqa: E402
from app.ai.errors import AIConfigError  # noqa: E402
from app.ai.llm import build_chat_model  # noqa: E402

SECRET = ""
failed = 0


def scrub(value: object) -> str:
    return str(value).replace(SECRET, "***") if SECRET else str(value)


def report(name: str, ok: bool, detail: object = "") -> None:
    global failed
    if not ok:
        failed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name}", flush=True)
    if detail:
        print(f"       {scrub(detail)}", flush=True)


class EventDraft(BaseModel):
    """조건 수집 스키마. 스키마 이름은 ASCII 만 허용된다(^[a-zA-Z0-9_-]+$)."""

    행사종류: str | None = Field(None, description="MT, 환영회 등. 없으면 null")
    예상인원: int | None = Field(None, description="말하지 않았으면 null")
    미정항목: list[str] = Field(default_factory=list, description="정해지지 않은 항목")


@tool
def get_event_headcount(event_id: str) -> int:
    """행사의 현재 확정 인원을 조회한다."""
    return 32


def main() -> int:
    global SECRET

    try:
        settings = AISettings()
        settings.require_api()
    except AIConfigError as e:
        report("설정 로드", False, e)
        return 1
    SECRET = settings.api_key.get_secret_value()
    report("설정 로드", True, f"base_url={settings.api_base_url} model={settings.model}")

    # 인증·모델명·호출 경로
    try:
        res = build_chat_model(settings).invoke("한 단어로만 답해. 대한민국의 수도는?")
        report("기본 호출", bool(res.text.strip()), f"응답={res.text!r}")
        report("토큰 사용량", res.usage_metadata is not None, res.usage_metadata)
    except Exception as e:
        report("기본 호출", False, f"{type(e).__name__}: {e}")

    # 구조화 출력. 조건을 말하지 않으면 null 로 두는지도 함께 본다
    try:
        structured = build_chat_model(settings).with_structured_output(
            EventDraft, method="json_schema"
        )
        out = structured.invoke("다음 달에 MT를 가고 싶어. 인원은 아직 몰라.")
        report("구조화 출력(json_schema)", isinstance(out, EventDraft), out)
        report("말하지 않은 값을 채우지 않음", out.예상인원 is None, f"예상인원={out.예상인원}")
    except Exception as e:
        report("구조화 출력(json_schema)", False, f"{type(e).__name__}: {e}")

    # Tool 왕복. chat/completions 에서는 여기서 400 이 난다
    try:
        model = build_chat_model(settings).bind_tools([get_event_headcount])
        messages: list = [("human", "evt_001 행사의 확정 인원을 알려줘.")]
        first = model.invoke(messages)
        report("tool 호출 요청", bool(first.tool_calls), [c["name"] for c in first.tool_calls])

        messages.append(first)
        for call in first.tool_calls:
            messages.append(get_event_headcount.invoke(call))
        final = model.invoke(messages)
        report("tool 결과 반영", "32" in final.text, f"최종 답변={final.text!r}")
    except Exception as e:
        report("tool 왕복", False, f"{type(e).__name__}: {e}")

    # 추론 깊이 조절. none 이면 추론 토큰이 0 이어야 한다
    for effort in ("none", "high"):
        try:
            res = build_chat_model(settings, reasoning={"effort": effort}).invoke(
                "참가자 32명, 예산 160만원이면 1인당 얼마인가? 계산 과정을 보여라."
            )
            used = (res.usage_metadata or {}).get("output_token_details", {}).get("reasoning")
            ok = used == 0 if effort == "none" else used is not None
            report(f"추론 깊이 effort={effort}", ok, f"reasoning_tokens={used}")
        except Exception as e:
            report(f"추론 깊이 effort={effort}", False, f"{type(e).__name__}: {e}")

    print(f"\n--- {'실패 ' + str(failed) + '건' if failed else '모두 통과'} ---")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
