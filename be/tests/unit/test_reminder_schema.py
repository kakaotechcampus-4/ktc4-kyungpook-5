"""정확한 항목 시각·시간대·알림 시각의 요청 계약."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.reminders import ReminderRecipientOut, TaskSuggestionConfirmIn


def _body() -> dict:
    return {"expectedVersion": 1, "kind": "TASK", "title": "자료 준비",
            "dueAt": "2030-10-19T15:00:00+09:00", "timezone": "Asia/Seoul",
            "reminderAt": "2030-10-19T14:00:00+09:00", "recipientAccountIds": ["acc_test"]}


def test_naive_time_and_unknown_timezone_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskSuggestionConfirmIn.model_validate({**_body(), "reminderAt": "2030-10-19T14:00:00"})
    with pytest.raises(ValidationError):
        TaskSuggestionConfirmIn.model_validate({**_body(), "timezone": "Not/AZone"})


def test_task_and_schedule_exact_times_are_explicit() -> None:
    body = {**_body(), "kind": "SCHEDULE"}
    with pytest.raises(ValidationError):
        TaskSuggestionConfirmIn.model_validate(body)
    body["scheduledAt"] = body.pop("dueAt")
    valid = TaskSuggestionConfirmIn.model_validate(body)
    assert valid.scheduled_at is not None and valid.due_at is None
    with pytest.raises(ValidationError):
        TaskSuggestionConfirmIn.model_validate({**body, "reminderAt": "2030-10-19T16:00:00+09:00"})


def test_equivalent_inputs_normalize_utc_and_unique_recipients() -> None:
    parsed = TaskSuggestionConfirmIn.model_validate({**_body(), "recipientAccountIds": ["acc_b", "acc_a", "acc_b"]})
    assert parsed.due_at == datetime(2030, 10, 19, 6, tzinfo=UTC)
    assert parsed.recipient_account_ids == ["acc_a", "acc_b"]


def test_recipient_contract_only_exposes_chair_and_officers() -> None:
    fields = {"accountId": "acc_test", "memberId": "mbr_test", "name": "운영진"}
    for role in ("OWNER", "MANAGER"):
        assert ReminderRecipientOut.model_validate({**fields, "role": role}).role == role
    with pytest.raises(ValidationError):
        ReminderRecipientOut.model_validate({**fields, "role": "MEMBER"})
