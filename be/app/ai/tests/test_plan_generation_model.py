"""생성 graph의 기본 경로가 실제 SDK 요청에 출력 한도·스트리밍을 지정하는지 확인한다."""

import asyncio
import json

import httpx

from app.ai.config import AISettings
from app.ai.features.planning.generation import model as plan_model
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.llm import build_chat_model
from app.ai.tests.test_plan_generation_graph import composition, request
from app.ai.tests.test_structured_output import _response


def test_default_graph_uses_streaming_budget_and_validates_complete_preview(monkeypatch):
    bodies = []
    text = composition().model_dump_json()
    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        final = _response([dict(type="output_text", text=text, annotations=[])])
        final["text"] = body["text"]
        events = [dict(type="response.created", response={**final, "output": [], "status": "in_progress"}),
            dict(type="response.output_text.delta", item_id="msg_test", output_index=0, content_index=0, delta=text),
            dict(type="response.completed", response=final)]
        stream = "".join(f"data: {json.dumps(dict(e, sequence_number=i))}\n\n" for i,e in enumerate(events))
        return httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            settings = AISettings(api_base_url="https://example.test/v1", api_key="secret", model="gpt-5.6-luna")
            monkeypatch.setattr(plan_model, "build_chat_model",
                lambda settings_arg=None, **kwargs: build_chat_model(settings, http_async_client=client, **kwargs))
            return await run_plan_generation(request())

    result = asyncio.run(run())
    assert result.status == "generated"
    assert result.preview.steps[0].name == "장소·교통 알아보기"
    assert len(bodies) == result.model_calls == 1
    assert bodies[0]["stream"] is True
    assert bodies[0]["max_output_tokens"] == plan_model.PLAN_MAX_OUTPUT_TOKENS == 8192
    assert bodies[0]["text"]["format"]["type"] == "json_schema"
