"""계획 수정 후 AI 검토 API 테스트 (#177).

app.ai.review_plan_edit()는 실제 모델 호출이라 monkeypatch로 결과를 고정하고,
버전 확인·상태 저장·늦은 결과 버림·시간 초과 투영만 검증한다.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

import app.ai as ai
from app.core.enums import EventStatus, PlanReviewStatus, StepCode
from app.db import session as db_session
from app.models.events import Event, PlanReview
from app.services import plan_review_service
from tests.integration.event_seed import add_event, owner_with_club
from tests.integration.test_events_planning import _create_event, _fake_generation_result

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
async def app_db(
    migrated_db_url: str, monkeypatch: pytest.MonkeyPatch, clear_db_caches: None
) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", migrated_db_url)
    yield
    await db_session.get_engine().dispose()


async def _revision(event_id: str) -> int:
    async with db_session.get_sessionmaker()() as session:
        return await session.scalar(select(Event.plan_revision).where(Event.id == event_id))


async def _review_row(event_id: str) -> PlanReview | None:
    async with db_session.get_sessionmaker()() as session:
        return await session.scalar(select(PlanReview).where(PlanReview.event_id == event_id))


def _generated_event(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, str]:
    """초안까지 만든 PLANNING 행사의 (인증 헤더, eventId)."""
    headers, club_id = owner_with_club(client, "review-owner")
    event_id = _create_event(client, headers, club_id)

    async def fake_generate(request):
        return _fake_generation_result()

    monkeypatch.setattr("app.ai.generate_planning_preview", fake_generate)
    res = client.post(
        f"/api/v1/events/{event_id}/plan/generate", headers=headers, json={"baseRevision": 0}
    )
    assert res.status_code == 200, res.text
    return headers, event_id


def _issues() -> ai.PlanEditReviewResult:
    return ai.PlanEditReviewResult(
        outcome="issues",
        items=(
            ai.PlanReviewItem(
                step_codes=(StepCode.DEMAND_SURVEY,),
                kind="missing_step",
                message="수요 조사를 빼면 인원을 미리 알기 어려워요.",
                suggestion="사전 수요 조사를 다시 넣어 보세요.",
            ),
        ),
    )


def _patch_review(monkeypatch: pytest.MonkeyPatch, outcome) -> list:
    """review_plan_edit을 고정한다. outcome이 예외면 던진다. 받은 요청 목록을 돌려준다."""
    calls: list = []

    async def fake_review(request):
        calls.append(request)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr("app.ai.review_plan_edit", fake_review)
    return calls


def _post_review(client: TestClient, headers: dict, event_id: str, revision: int):
    return client.post(
        f"/api/v1/events/{event_id}/plan/review",
        headers=headers,
        json={"expectedRevision": revision},
    )


async def test_검토하면_DONE과_주의점을_돌려준다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    calls = _patch_review(monkeypatch, _issues())
    revision = await _revision(event_id)

    res = _post_review(client, headers, event_id, revision)

    assert res.status_code == 200, res.text
    review = res.json()["data"]
    assert review["status"] == "DONE"
    assert review["reviewedRevision"] == revision
    assert review["generatedRevision"] == revision
    assert review["outcome"] == "issues"
    assert review["errorCode"] is None
    assert review["items"][0]["stepCodes"] == ["DEMAND_SURVEY"]
    assert review["items"][0]["stepNames"] == ["사전 수요 조사"]
    assert review["items"][0]["kind"] == "missing_step"
    assert review["items"][0]["suggestion"] == "사전 수요 조사를 다시 넣어 보세요."
    # 요청은 지금 계획과 생성 직후 기준으로 만든다.
    assert len(calls) == 1
    assert [s.code for s in calls[0].included_steps] == [
        StepCode.RESEARCH_VENUE,
        StepCode.COLLECT_FEES,
    ]
    assert calls[0].draft.conditions.headcount == 30
    excluded = {s.code: s.excluded_by for s in calls[0].excluded_steps}
    assert excluded[StepCode.DEMAND_SURVEY] == "ai"

    screen = client.get(f"/api/v1/events/{event_id}/plan", headers=headers)
    assert screen.status_code == 200, screen.text
    data = screen.json()["data"]
    assert data["planRevision"] == revision
    assert data["review"] == review


async def test_버전이_다르면_409(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    calls = _patch_review(monkeypatch, _issues())
    revision = await _revision(event_id)

    res = _post_review(client, headers, event_id, revision - 1)

    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "VERSION_CONFLICT"
    assert calls == []


async def test_초안_전에는_검토할_수_없다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = owner_with_club(client, "review-before")
    event_id = _create_event(client, headers, club_id)
    calls = _patch_review(monkeypatch, _issues())

    screen = client.get(f"/api/v1/events/{event_id}/plan", headers=headers)
    assert screen.status_code == 200, screen.text
    assert screen.json()["data"]["review"] is None
    assert screen.json()["data"]["planRevision"] == 0

    res = _post_review(client, headers, event_id, 0)
    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "EVENT_STATE_CONFLICT"
    assert calls == []


async def test_계획_중이_아니면_409(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, club_id = owner_with_club(client, "review-ongoing")
    event_id = await add_event(club_id, status=EventStatus.ON_GOING)
    calls = _patch_review(monkeypatch, _issues())

    res = _post_review(client, headers, event_id, 0)

    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "EVENT_STATE_CONFLICT"
    assert calls == []


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ai.AIInvalidResponseError("형식 오류"), "AI_INVALID_RESPONSE"),
        (ai.AIRetryableError("일시 오류"), "AI_UNAVAILABLE"),
        (ai.AITimeoutError("시간 초과"), "AI_UNAVAILABLE"),
        (ai.AIConfigError("설정 오류"), "AI_MISCONFIGURED"),
    ],
)
async def test_AI_응답_오류는_FAILED로_저장한다(
    client: TestClient,
    app_db: None,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    code: str,
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    _patch_review(monkeypatch, error)
    revision = await _revision(event_id)

    res = _post_review(client, headers, event_id, revision)

    assert res.status_code == 200, res.text
    review = res.json()["data"]
    assert review["status"] == "FAILED"
    assert review["errorCode"] == code
    assert review["items"] == []
    row = await _review_row(event_id)
    assert row.status == PlanReviewStatus.FAILED
    assert row.error_code == code
    assert row.finished_at is not None


async def test_AI가_아닌_오류도_검토_중에_갇히지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    _patch_review(monkeypatch, RuntimeError("버그"))
    revision = await _revision(event_id)

    with pytest.raises(RuntimeError):
        _post_review(client, headers, event_id, revision)

    row = await _review_row(event_id)
    assert row.status == PlanReviewStatus.FAILED
    assert row.error_code == "INTERNAL_ERROR"


async def test_같은_버전_DONE은_다시_부르지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    calls = _patch_review(monkeypatch, _issues())
    revision = await _revision(event_id)

    first = _post_review(client, headers, event_id, revision)
    second = _post_review(client, headers, event_id, revision)

    assert first.status_code == 200 and second.status_code == 200, second.text
    assert second.json()["data"] == first.json()["data"]
    assert len(calls) == 1


async def test_FAILED는_다시_부른다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    calls = _patch_review(monkeypatch, ai.AIRetryableError("일시 오류"))
    revision = await _revision(event_id)
    failed = _post_review(client, headers, event_id, revision)
    assert failed.json()["data"]["status"] == "FAILED"

    retry_calls = _patch_review(monkeypatch, _issues())
    retried = _post_review(client, headers, event_id, revision)

    assert retried.status_code == 200, retried.text
    assert retried.json()["data"]["status"] == "DONE"
    assert retried.json()["data"]["errorCode"] is None
    assert len(calls) == 1
    assert len(retry_calls) == 1


async def test_검토_중인_같은_버전은_다시_부르지_않는다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    calls = _patch_review(monkeypatch, _issues())
    revision = await _revision(event_id)
    async with db_session.get_sessionmaker()() as session:
        await session.execute(
            update(PlanReview)
            .where(PlanReview.event_id == event_id)
            .values(
                status=PlanReviewStatus.REVIEWING,
                request_id="in-flight",
                reviewed_revision=revision,
                requested_at=datetime.now(UTC) - timedelta(seconds=10),
            )
        )
        await session.commit()

    res = _post_review(client, headers, event_id, revision)

    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "REVIEWING"
    assert calls == []


async def test_재생성으로_바뀐_뒤_도착한_결과는_버린다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    revision = await _revision(event_id)

    async def regenerate_then_answer(request):
        # AI를 기다리는 사이 재생성이 검토 행을 새 기준으로 바꾼 상황.
        async with db_session.get_sessionmaker()() as session:
            await plan_review_service.reset_baseline(session, event_id, revision + 1)
            await session.commit()
        return _issues()

    monkeypatch.setattr("app.ai.review_plan_edit", regenerate_then_answer)

    res = _post_review(client, headers, event_id, revision)

    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "NOT_REQUESTED"
    row = await _review_row(event_id)
    assert row.status == PlanReviewStatus.NOT_REQUESTED
    assert row.items is None
    assert row.generated_revision == revision + 1


async def test_오래된_REVIEWING은_시간_초과로_보인다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, event_id = _generated_event(client, monkeypatch)
    calls = _patch_review(monkeypatch, _issues())
    revision = await _revision(event_id)
    async with db_session.get_sessionmaker()() as session:
        await session.execute(
            update(PlanReview)
            .where(PlanReview.event_id == event_id)
            .values(
                status=PlanReviewStatus.REVIEWING,
                request_id="lost",
                reviewed_revision=revision,
                requested_at=datetime.now(UTC) - timedelta(seconds=91),
            )
        )
        await session.commit()

    screen = client.get(f"/api/v1/events/{event_id}/plan", headers=headers)
    assert screen.status_code == 200, screen.text
    review = screen.json()["data"]["review"]
    assert review["status"] == "FAILED"
    assert review["errorCode"] == "REVIEW_TIMEOUT"
    # 응답에서만 바꿔 보이고 DB는 그대로 둔다.
    assert (await _review_row(event_id)).status == PlanReviewStatus.REVIEWING

    res = _post_review(client, headers, event_id, revision)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "DONE"
    assert len(calls) == 1


async def test_비회원은_검토할_수_없다(
    client: TestClient, app_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _headers, event_id = _generated_event(client, monkeypatch)
    calls = _patch_review(monkeypatch, _issues())
    revision = await _revision(event_id)
    outsider, _club = owner_with_club(client, "review-outsider")

    res = _post_review(client, outsider, event_id, revision)

    assert res.status_code == 403, res.text
    assert calls == []
