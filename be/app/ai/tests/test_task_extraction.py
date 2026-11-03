"""공개 후보 추출 계약과 모델 호출 경계를 검증한다."""

import asyncio
import json

import pytest
from pydantic import ValidationError

import app.ai as ai
from app.ai.features.meeting import task_extraction


def request(**changes):
    def item(seq, text):
        return {"utterance_id": f"u-{seq}", "seq": seq, "version": 1, "text": text,
                "started_at": "2026-10-19T10:00:00+09:00", "ended_at": "2026-10-19T10:00:01+09:00"}
    values = {"meeting_id": "m1", "club_id": "c1", "utterance": item(6, "민수가 금요일까지 자료 정리하고 토요일 14시에 회의합시다"),
              "context": [item(i, f"이전 발화 {i}") for i in range(1, 6)],
              "timezone": "Asia/Seoul", "occurred_at": "2026-10-19T01:00:00+00:00"}
    return ai.TaskExtractionRequest.model_validate(values | changes)


def test_public_extract_returns_multiple_be_shaped_candidates(monkeypatch):
    async def invoke(messages, schema):
        data = json.loads(messages[1].content)
        assert data["context"] == [f"이전 발화 {i}" for i in range(2, 6)]
        assert data["occurred_at"] == "2026-10-19T10:00:00+09:00"
        return schema.model_validate({"suggestions": [
            {"kind": "TASK", "title": "자료 정리", "suggested_assignee": "민수",
             "due_date": "2026-10-23", "unresolved_fields": ["due_at"]},
            {"kind": "SCHEDULE", "title": "회의", "scheduled_at": "2026-10-24T14:00:00+09:00",
             "unresolved_fields": ["suggested_assignee"]},
        ]})
    monkeypatch.setattr(task_extraction, "ainvoke_structured", invoke)
    result = asyncio.run(ai.extract_task_suggestions(request()))
    assert len(result.suggestions) == 2
    assert result.suggestions[0].model_dump()["suggested_assignee"] == "민수"
    assert set(result.suggestions[1].model_dump()) == {"kind", "title", "description", "suggested_assignee", "due_date", "due_at", "scheduled_at", "unresolved_fields"}


def test_empty_and_failure_remain_distinct(monkeypatch):
    async def empty(messages, schema):
        return schema(suggestions=[])
    monkeypatch.setattr(task_extraction, "ainvoke_structured", empty)
    assert asyncio.run(ai.extract_task_suggestions(request())).suggestions == []
    async def failure(messages, schema):
        raise ai.AIRetryableError("모델 실패")
    monkeypatch.setattr(task_extraction, "ainvoke_structured", failure)
    with pytest.raises(ai.AIRetryableError):
        asyncio.run(ai.extract_task_suggestions(request()))


def test_rejects_invalid_timezone_naive_dates_extra_fields_and_bad_context():
    with pytest.raises(ValidationError):
        request(timezone="없는/시간대")
    with pytest.raises(ValidationError):
        request(occurred_at="2026-10-19T10:00:00")
    with pytest.raises(ValidationError):
        request(context=[request().utterance])
    with pytest.raises(ValidationError):
        ai.TaskSuggestion(kind="TASK", title="자료 정리", due_at="2026-10-23T10:00:00")
    with pytest.raises(ValidationError):
        ai.TaskSuggestion(kind="TASK", title="자료 정리", recipient_account_ids=["x"])


def test_missing_confirmation_fields_are_added_without_inventing_times():
    task = ai.TaskSuggestion(kind="TASK", title="자료 정리", due_date="2026-10-23",
                             unresolved_fields=["description", "description"])
    assert task.due_date.isoformat() == "2026-10-23"
    assert task.due_at is None
    assert task.unresolved_fields == ["description", "due_at", "suggested_assignee"]
    schedule = ai.TaskSuggestion(kind="SCHEDULE", title="회의", suggested_assignee="  ",
                                 unresolved_fields=["scheduled_at"])
    assert schedule.scheduled_at is None
    assert schedule.unresolved_fields == ["scheduled_at", "suggested_assignee"]
    complete = ai.TaskSuggestion(kind="TASK", title="자료 정리", suggested_assignee="민수",
                                 due_at="2026-10-23T18:00:00+09:00")
    assert complete.unresolved_fields == []


def test_multiple_tasks_keep_each_optional_description(monkeypatch):
    async def invoke(messages, schema):
        data = json.loads(messages[1].content)
        assert "자료 정리" in data["utterance"]
        assert "장소 예약" in data["utterance"]
        return schema.model_validate({"suggestions": [
            {"kind": "TASK", "title": "자료 정리", "description": "지난 행사 자료 포함\n사진도 정리"},
            {"kind": "TASK", "title": "장소 예약", "description": "참석 인원 확인 후 예약"},
            {"kind": "TASK", "title": "안내문 작성", "description": None},
        ]})

    monkeypatch.setattr(task_extraction, "ainvoke_structured", invoke)
    original = request()
    utterance = original.utterance.model_copy(update={
        "text": "자료 정리는 지난 행사 자료와 사진도 포함하고, 장소 예약은 참석 인원 확인 후 해요. 안내문도 작성합시다."
    })
    result = asyncio.run(ai.extract_task_suggestions(original.model_copy(update={"utterance": utterance})))
    assert [(item.title, item.model_dump()["description"]) for item in result.suggestions] == [
        ("자료 정리", "지난 행사 자료 포함\n사진도 정리"),
        ("장소 예약", "참석 인원 확인 후 예약"),
        ("안내문 작성", None),
    ]
