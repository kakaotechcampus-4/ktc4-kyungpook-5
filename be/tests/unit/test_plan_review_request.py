from datetime import date, datetime

from app import ai
from app.ai.planning_catalog import PLANNING_STEP_NAMES
from app.core.enums import ActionType, StepCode
from app.services import plan_review_service as svc

TODAY = date(2026, 11, 1)
ALL = list(PLANNING_STEP_NAMES)


def _step(code, starts=None, deadline=None, actions=()):
    return {
        "code": code.value,
        "starts_at": starts,
        "deadline": deadline,
        "actions": list(actions),
    }


def _plan(codes, **overrides):
    steps = []
    for code in codes:
        steps.append(overrides.get(code, _step(code)))
    return {"steps": steps}


def _build(current, baseline, ai_excluded=()):
    return svc.build_review_request(
        draft=ai.PlanningDraft(),
        today=TODAY,
        current=current,
        baseline=baseline,
        ai_excluded=list(ai_excluded),
    )


def _catalog_without(*skip):
    return [c for c in ALL if c not in skip]


def test_사용자가_뺀_단계와_AI가_뺀_단계를_구분한다():
    base = _plan(_catalog_without(StepCode.REFUND_FEES))
    cur = _plan(_catalog_without(StepCode.REFUND_FEES, StepCode.DEMAND_SURVEY))
    req = _build(cur, base, [{"code": "REFUND_FEES", "name": "참가비 환급", "reason": "무료 행사"}])
    by = {e.code: e for e in req.excluded_steps}
    assert by[StepCode.DEMAND_SURVEY].excluded_by == "user"
    assert by[StepCode.REFUND_FEES].excluded_by == "ai"
    assert by[StepCode.REFUND_FEES].reason == "무료 행사"
    assert req.changes.removed_codes == (StepCode.DEMAND_SURVEY,)


def test_AI가_뺐던_단계를_다시_넣으면_added에_들어간다():
    base = _plan(_catalog_without(StepCode.REFUND_FEES))
    cur = _plan(ALL)
    req = _build(cur, base, [{"code": "REFUND_FEES", "name": "참가비 환급", "reason": "x"}])
    assert req.changes.added_codes == (StepCode.REFUND_FEES,)
    assert StepCode.REFUND_FEES not in {e.code for e in req.excluded_steps}


def test_묶음_안_순서가_바뀐_단계만_moved에_들어간다():
    base = _plan(ALL)
    swapped = list(ALL)
    i, j = swapped.index(StepCode.CONFIRM_DETAILS), swapped.index(StepCode.BOOK_VENUE)
    swapped[i], swapped[j] = swapped[j], swapped[i]
    req = _build(_plan(swapped), base)
    assert set(req.changes.moved_codes) == {StepCode.BOOK_VENUE, StepCode.CONFIRM_DETAILS}


def test_일정과_금액_변경을_전후로_담는다():
    fee = {"type": "TRANSFER", "title": "참가비", "amount": 30000, "due_date": None}
    base = _plan(ALL, **{StepCode.COLLECT_FEES: _step(
        StepCode.COLLECT_FEES, deadline="2026-11-10T00:00:00+09:00", actions=[fee])})
    cur = _plan(ALL, **{StepCode.COLLECT_FEES: _step(
        StepCode.COLLECT_FEES, deadline="2026-11-12T00:00:00+09:00",
        actions=[{**fee, "amount": 25000}])})
    req = _build(cur, base)
    assert len(req.changes.schedule_changes) == 1
    sc = req.changes.schedule_changes[0]
    assert sc.code == StepCode.COLLECT_FEES
    assert sc.before_deadline == datetime.fromisoformat("2026-11-10T00:00:00+09:00")
    assert sc.after_deadline == datetime.fromisoformat("2026-11-12T00:00:00+09:00")
    assert req.changes.action_changes == (
        ai.ActionChange(code=StepCode.COLLECT_FEES, action_title="참가비",
                        field="amount", before="30000", after="25000"),
    )
    step = next(s for s in req.included_steps if s.code == StepCode.COLLECT_FEES)
    assert step.actions[0].type == ActionType.TRANSFER
    assert step.actions[0].amount == 25000


def test_일정이_없어도_차이를_만든다():
    req = _build(_plan(ALL), _plan(ALL))
    assert req.changes.schedule_changes == ()
    assert req.model_dump_json()


def _deadline_plan(value, due=None):
    fee = {"type": "TRANSFER", "title": "참가비", "amount": 30000, "due_date": due}
    return _plan(ALL, **{StepCode.COLLECT_FEES: _step(
        StepCode.COLLECT_FEES, starts=value, deadline=value, actions=[fee])})


def test_같은_순간이면_시간대_표기가_달라도_일정_변경이_아니다():
    base = _deadline_plan("2026-11-23T00:00:00+09:00")
    cur = _deadline_plan("2026-11-22T15:00:00+00:00")
    assert _build(cur, base).changes.schedule_changes == ()


def test_시간대_표기가_달라도_실제_일정_변경은_담는다():
    base = _deadline_plan("2026-11-23T00:00:00+09:00")
    cur = _deadline_plan("2026-11-23T15:00:00+00:00")
    changes = _build(cur, base).changes.schedule_changes
    assert len(changes) == 1
    assert changes[0].code == StepCode.COLLECT_FEES


def test_iso는_시각을_UTC로_쓰고_날짜는_그대로_둔다():
    assert svc._iso(datetime.fromisoformat("2026-11-23T00:00:00+09:00")) == "2026-11-22T15:00:00+00:00"
    assert svc._iso(date(2026, 11, 23)) == "2026-11-23"
    assert svc._iso(None) is None
