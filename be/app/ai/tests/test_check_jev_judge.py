"""Jev 측정 스크립트가 요청을 Laya와 같은 형식으로 보내고 응답에서 조회 확률을 읽는지 검증한다(#245).

실제 Jev는 부르지 않는다. 같은 입력 글과 같은 판단 질문을 보내야 luna·Laya와 같은 문항으로 견줄 수 있다.
"""

import json

import httpx

from app.ai.features.meeting.questions import judge_questions
from app.ai.scripts.check_jev_judge import JevClient, _judge


def _client(base_url: str, handler) -> JevClient:
    client = JevClient(base_url, "test-key", "typesafe/jev-1.14", timeout=1)
    client.http = httpx.Client(
        transport=httpx.MockTransport(handler), headers=client.http.headers, timeout=1
    )
    return client


def test_sends_state_and_questions_to_decisions_and_reads_noul():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "typesafe/jev-1.14-20261014",
            "answers": {"record_lookup": {"type": "noul", "noul": 0.94}},
            "usage": {"prompt_tokens": 424, "completion_tokens": 0},
        })

    questions = judge_questions()
    outcome = _client("https://mlapi.example/abc", handler).decide("[방금 발화]\n그때 숙소비 얼마였지?", questions)

    assert seen["url"] == "https://mlapi.example/abc/v1/decisions"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"] == {
        "model": "typesafe/jev-1.14",
        "state": "[방금 발화]\n그때 숙소비 얼마였지?",
        "questions": questions,
    }
    assert (outcome["p_true"], outcome["prompt_tokens"], outcome["served_model"]) == (
        0.94, 424, "typesafe/jev-1.14-20261014"
    )


def test_base_url_ending_in_v1_is_not_doubled():
    client = JevClient("https://mlapi.example/abc/v1/", "k", "m", timeout=1)
    assert client.url == "https://mlapi.example/abc/v1/decisions"


def test_failed_call_is_recorded_without_request_details():
    # 실패한 문항은 판단에서 빼고 오류로 센다. 키가 섞일 수 있는 요청 내용은 남기지 않는다
    client = _client("https://mlapi.example/abc", lambda request: httpx.Response(429, json={"error": "rate"}))
    assert _judge(client, "state", judge_questions()) == {"error": "HTTPStatusError 429"}
