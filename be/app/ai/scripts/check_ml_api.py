"""ML API 연결과 기능 지원 범위를 실제 호출로 확인한다. 채팅 모델과 임베딩 모델을 함께 본다.

키가 필요해 CI에서 돌리지 않는다. 게이트웨이·모델을 바꿀 때 수동으로 실행한다.

    cd be && uv run python app/ai/scripts/check_ml_api.py

AI_* 는 be/.env 에서 읽는다. 출력은 모두 scrub()을 거쳐 키가 남지 않는다.
"""

from math import sqrt
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field

load_dotenv(Path(".env").resolve(), override=True)

from app.ai.config import AISettings  # noqa: E402
from app.ai.errors import AIConfigError  # noqa: E402
from app.ai.llm import EMBEDDING_DIMENSIONS, build_chat_model, build_embeddings  # noqa: E402

SECRETS: list[str] = []
failed = 0


def scrub(value: object) -> str:
    """출력에서 키를 가린다. 채팅·임베딩 키가 다를 수 있어 아는 값을 모두 지운다."""
    text = str(value)
    for secret in SECRETS:
        if secret:
            text = text.replace(secret, "***")
    return text


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


def cosine(a: list[float], b: list[float]) -> float:
    """코사인 유사도. 검색 품질이 아니라 벡터가 말이 되는지만 본다."""
    dot = sum(x * y for x, y in zip(a, b))
    size = sqrt(sum(x * x for x in a)) * sqrt(sum(y * y for y in b))
    return dot / size if size else 0.0


def check_embeddings(settings: AISettings) -> None:
    """임베딩 배포의 연결·차원·배치와 dimensions 지원 여부를 본다.

    저장소(pgvector) 컬럼 차원이 여기서 나오는 길이에 묶이므로 차원을 먼저 확인한다.
    """
    try:
        settings.require_embedding()
    except AIConfigError as e:
        report("임베딩 설정", False, e)
        return
    report(
        "임베딩 설정",
        True,
        f"base_url={settings.embedding_base_url} model={settings.embedding_model}",
    )

    embeddings = build_embeddings(settings)

    try:
        vector = embeddings.embed_query("동아리 MT 참가비는 1인당 4만원이었다.")
        report("임베딩 호출", bool(vector), f"차원={len(vector)}")
        report(
            f"차원이 EMBEDDING_DIMENSIONS({EMBEDDING_DIMENSIONS})와 같음",
            len(vector) == EMBEDDING_DIMENSIONS,
            f"실제={len(vector)}",
        )
    except Exception as e:
        # 주소에 /v1 이 빠지면 .../embeddings 로 요청이 가서 404 가 난다.
        hint = (
            " — AI_EMBEDDING_BASE_URL 이 /v1 로 끝나는지 확인"
            if "404" in str(e) or "Not Found" in str(e)
            else ""
        )
        report("임베딩 호출", False, f"{type(e).__name__}: {e}{hint}")
        return

    # 색인은 여러 청크를 한 번에 보낸다. 문자열 배열을 받는지와 길이가 고른지를 본다.
    try:
        texts = [
            "작년 봄 MT는 32명이 참가했다.",
            "MT 참가 인원은 서른두 명이었다.",
            "오늘 학교 앞에 새로 생긴 카페가 맛있다.",
        ]
        vectors = embeddings.embed_documents(texts)
        ok = len(vectors) == len(texts) and {len(v) for v in vectors} == {
            EMBEDDING_DIMENSIONS
        }
        report("배치 임베딩", ok, f"개수={len(vectors)}")

        related = cosine(vectors[0], vectors[1])
        unrelated = cosine(vectors[0], vectors[2])
        report(
            "관련 문장이 무관한 문장보다 가깝다",
            related > unrelated,
            f"관련={related:.4f} 무관={unrelated:.4f}",
        )
    except Exception as e:
        report("배치 임베딩", False, f"{type(e).__name__}: {e}")

    # 차원을 줄여 저장하는 선택지가 열려 있는지만 확인한다. 실패해도 기본값을 쓰면 된다.
    try:
        short = build_embeddings(settings, dimensions=512).embed_query("차원 축소 확인")
        report("dimensions 파라미터 지원", len(short) == 512, f"차원={len(short)}")
    except Exception as e:
        report("dimensions 파라미터 지원", False, f"{type(e).__name__}: {e}")


def main() -> int:
    try:
        settings = AISettings()
    except Exception as e:  # 환경변수 형식 오류
        report("설정 로드", False, f"{type(e).__name__}: {e}")
        return 1
    SECRETS.extend(
        (
            settings.api_key.get_secret_value(),
            settings.resolved_embedding_api_key.get_secret_value(),
        )
    )
    try:
        settings.require_api()
    except AIConfigError as e:
        report("설정 로드", False, e)
        return 1
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

    check_embeddings(settings)

    print(f"\n--- {'실패 ' + str(failed) + '건' if failed else '모두 통과'} ---")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
