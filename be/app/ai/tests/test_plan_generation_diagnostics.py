"""실패 진단 결과에도 공급자 원문·키·헤더를 보존하지 않는다."""

import json

import httpx
import pytest

from app.ai.scripts.diagnose_plan_generation import response_summary


@pytest.mark.parametrize("streaming", [False, True])
def test_diagnostic_selects_only_safe_status_length_and_token_fields(streaming):
    data = dict(status="incomplete", incomplete_details={"reason": "max_output_tokens"},
        output=[dict(content=[dict(type="output_text", text='{"private":"secret-body')])],
        usage=dict(output_tokens=2000, output_tokens_details={"reasoning_tokens": 600}, hidden="secret-usage"),
        metadata={"secret": "secret-metadata"})
    response = (httpx.Response(200, text="data: " + json.dumps(dict(type="response.incomplete", response=data)) + "\n\n")
                if streaming else httpx.Response(200, json=data))
    summary = response_summary(response)
    assert summary["incomplete_reason"] == "max_output_tokens"
    assert summary["output_tokens"] == 2000 and summary["reasoning_tokens"] == 600
    assert summary["valid_json"] is False
    assert "secret" not in json.dumps(summary)


def test_missing_terminal_response_does_not_copy_unreadable_body():
    assert response_summary(httpx.Response(502, text="secret-error-body")) == {
        "http_status": 502, "terminal_response": False}
