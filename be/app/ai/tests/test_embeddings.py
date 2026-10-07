"""임베딩 호출이 벡터를 검증하고 모델 오류를 AI 오류 타입으로 바꾸는지 검증한다.

ML API 대신 가짜 HTTP 응답을 돌려줘 langchain-openai·openai의 실제 처리 경로를 탄다.
"""

import asyncio
import json

import httpx
import pytest

from app.ai.config import AISettings
from app.ai.contracts import SourceLocation
from app.ai.errors import (
    AIConfigError,
    AIInvalidResponseError,
    AIRetryableError,
    AITimeoutError,
)
from app.ai.features.retrieval.indexing import embedding_input
from app.ai.features.retrieval.schemas import TextChunk
from app.ai.llm import EMBEDDING_BATCH_SIZE, EMBEDDING_DIMENSIONS, aembed_texts, build_embeddings

API_KEY = "super-secret-key"


def _vector(seed: float, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    return [seed] + [0.0] * (dimensions - 1)


def _embeddings(vectors: list[list[float]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": [
                {"object": "embedding", "index": index, "embedding": vector}
                for index, vector in enumerate(vectors)
            ],
            "model": "text-embedding-3-small",
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        },
    )


def _echo(requests: list[httpx.Request] | None = None):
    """받은 글마다 순번을 첫 칸에 담은 벡터를 돌려준다"""
    count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal count
        if requests is not None:
            requests.append(request)
        texts = json.loads(request.content)["input"]
        vectors = [_vector(float(count + offset)) for offset in range(len(texts))]
        count += len(texts)
        return _embeddings(vectors)

    return handler


def _call(handler, texts=("회비", "장소")):
    settings = AISettings(
        api_base_url="https://example.test/v1",
        api_key=API_KEY,
        model="gpt-5.6-terra",
        embedding_base_url="https://example.test/embed/v1",
        embedding_model="text-embedding-3-small",
    )
    # 재시도는 SDK 동작이라 여기서는 끄고 변환만 본다.
    model = build_embeddings(
        settings,
        max_retries=0,
        http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return asyncio.run(aembed_texts(list(texts), model=model))


def test_보낸_순서대로_벡터를_돌려준다():
    vectors = _call(_echo(), texts=["회비", "장소", "인원"])

    assert [vector[0] for vector in vectors] == [0.0, 1.0, 2.0]
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors)


def test_글이_많으면_배치_크기만큼_나눠_요청한다():
    requests: list[httpx.Request] = []
    texts = [f"청크 {number}" for number in range(EMBEDDING_BATCH_SIZE * 2 + 50)]

    vectors = _call(_echo(requests), texts=texts)

    assert [len(json.loads(r.content)["input"]) for r in requests] == [100, 100, 50]
    assert [vector[0] for vector in vectors] == [float(n) for n in range(len(texts))]


def test_응답_벡터_개수가_다르면_AIInvalidResponseError():
    with pytest.raises(AIInvalidResponseError):
        _call(lambda request: _embeddings([_vector(0.0)]), texts=["회비", "장소"])


def test_응답_벡터_차원이_다르면_AIInvalidResponseError():
    short = [_vector(0.0, dimensions=512), _vector(1.0, dimensions=512)]

    with pytest.raises(AIInvalidResponseError):
        _call(lambda request: _embeddings(short))


def test_응답_시간_초과는_AITimeoutError():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    with pytest.raises(AITimeoutError):
        _call(handler)


@pytest.mark.parametrize(
    ("status", "expected"),
    [(500, AIRetryableError), (429, AIRetryableError), (401, AIConfigError)],
)
def test_HTTP_오류는_AI_오류_타입으로_바뀐다(status, expected):
    response = httpx.Response(status, json={"error": {"message": "gateway error"}})

    with pytest.raises(expected) as error:
        _call(lambda request: response, texts=["작년 봄 MT 회비"])

    assert API_KEY not in str(error.value)
    assert "작년 봄 MT 회비" not in str(error.value)


def test_임베딩_입력은_문서명과_위치를_본문_앞에_붙인다():
    chunk = TextChunk(
        text="수입: 회비 45,000원 × 28명 = 1,260,000원",
        location=SourceLocation(label="2쪽 · 3. 정산"),
        block_indexes=(1,),
    )

    text = embedding_input("2025 봄 MT 결과보고.pdf", chunk)

    assert text == (
        "문서: 2025 봄 MT 결과보고.pdf\n"
        "위치: 2쪽 · 3. 정산\n"
        "\n"
        "수입: 회비 45,000원 × 28명 = 1,260,000원"
    )
    assert chunk.text.startswith("수입:")  # 청크 원문은 그대로다
