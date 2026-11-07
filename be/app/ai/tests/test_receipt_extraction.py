"""영수증 이미지 추출 계약과 비전 입력 경계를 검증한다."""

import asyncio
import base64
import json

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError

import app.ai as ai
from app.ai.features.accounting import receipt_extraction


def request(**changes):
    values = {
        "file_name": "receipt.jpg",
        "mime_type": "image/jpeg",
        "image_bytes": b"image-bytes",
    }
    return ai.ExtractReceiptRequest.model_validate(values | changes)


def test_public_extract_sends_data_url_and_preserves_read_values(monkeypatch):
    async def invoke(messages, schema):
        assert isinstance(messages[1], HumanMessage)
        text, image = messages[1].content
        assert json.loads(json.dumps(text)) == {"type": "text", "text": "파일명: receipt.jpg"}
        assert image["type"] == "image_url"
        assert image["image_url"]["url"] == (
            "data:image/jpeg;base64," + base64.b64encode(b"image-bytes").decode()
        )
        return schema.model_validate({"rows": [{
            "spent_at": "2026-12-31",
            "merchant": "가게",
            "amount": 12000,
            "category": "식비",
            "description": "김밥",
        }]})

    monkeypatch.setattr(receipt_extraction, "ainvoke_structured", invoke)
    result = asyncio.run(ai.extract_receipt(request()))
    assert result.rows[0].model_dump() == {
        "spent_at": __import__("datetime").date(2026, 12, 31),
        "merchant": "가게",
        "amount": 12000,
        "category": "식비",
        "description": "김밥",
    }


def test_unreadable_is_empty_and_model_failure_is_raised(monkeypatch):
    async def empty(messages, schema):
        return schema.model_validate({"rows": []})

    monkeypatch.setattr(receipt_extraction, "ainvoke_structured", empty)
    assert asyncio.run(ai.extract_receipt(request())).rows == ()

    async def failure(messages, schema):
        raise ai.AIRetryableError("모델 실패")

    monkeypatch.setattr(receipt_extraction, "ainvoke_structured", failure)
    with pytest.raises(ai.AIRetryableError):
        asyncio.run(ai.extract_receipt(request()))


def test_receipt_contract_rejects_guesses_invalid_images_and_extra_fields():
    empty_row = {"spent_at": None, "merchant": None, "amount": None,
                 "category": None, "description": None}
    assert ai.ExtractedReceiptRow(**empty_row).model_dump() == empty_row
    with pytest.raises(ValidationError):
        request(mime_type="application/pdf")
    with pytest.raises(ValidationError):
        request(image_bytes=b"")
    with pytest.raises(ValidationError):
        ai.ExtractedReceiptRow(**(empty_row | {"spent_at": "2026", "amount": 1000}))
    with pytest.raises(ValidationError):
        ai.ExtractedReceiptRow(**(empty_row | {"amount": -1}))
    with pytest.raises(ValidationError):
        ai.ExtractedReceiptRow(**(empty_row | {"raw_fields": {"source": "model"}}))


def test_structured_schema_requires_nullable_fields():
    schema = convert_to_openai_tool(ai.ExtractReceiptResult, strict=True)["function"]["parameters"]
    assert set(schema["properties"]["rows"]["items"]["required"]) == {
        "spent_at", "merchant", "amount", "category", "description"
    }
