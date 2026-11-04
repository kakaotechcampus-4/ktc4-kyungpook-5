"""실제 graph/검증은 유지하고 모델만 고정해 진행 알림의 진실성과 결과 보존을 검사한다."""

import asyncio
from functools import partial

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError

import app.ai as ai
from app.ai.contracts import RecordLookupResult, RecordSearchResult
from app.ai.features.planning import public_workflow as workflow
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent import nodes
from app.ai.features.planning.agent.tools import UpdateEventConditionsInput, update_event_conditions
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.features.planning.progress import condition_progress, notify, started
from app.ai.tests.test_plan_generation_graph import Model
from app.ai.tests.test_planning_agent_generation import request, change_call, gen_call
from app.ai.tests.test_planning_agent_parallel_tools import defer_call, C2
from app.ai.tests.test_planning_agent_records import Port, chunk, lookup, search_call
from app.ai.tests.test_planning_public_workflow import request as public_request, button, scripted, tool


class Recorder:
    def __init__(self, *, broken=False):
        self.events = []
        self.broken = broken

    async def progress(self, event):
        self.events.append(event)
        if self.broken:
            raise RuntimeError("private provider payload")

    async def reply_delta(self, text):
        pass

    async def reply_reset(self):
        pass


def run_turn(req, calls, *, progress=None, search=None, model=None):
    responses = iter([AIMessage(id="assistant-tools", content="", tool_calls=calls),
                      AIMessage(id="assistant-reply", content="처리 결과를 확인해 주세요.")])

    async def invoke(*args, **kwargs):
        return next(responses)

    return asyncio.run(run_planning_agent_turn(
        req, invoke=invoke, search=search, progress=progress,
        generate=partial(run_plan_generation, invoke=model or Model()),
    ))


def test_change_and_defer_only_reports_actual_condition_change():
    req = request(C2)
    port = Recorder()
    result = run_turn(req, [change_call(req, "headcount", 60), defer_call(req)], progress=port)
    assert result.draft.conditions.headcount == 60
    assert [(e.kind, e.status, e.text) for e in port.events] == [
        ("condition_applied", "completed", "예상 인원 반영했어요")]


@pytest.mark.parametrize("mode", ["rejected", "unchanged", "defer_only"])
def test_no_false_condition_completion(mode):
    req = request()
    args = change_call(req, "headcount", 60)["args"]
    if mode == "rejected":
        args["changes"][0]["evidence"]["quote"] = "없는 발화"
    elif mode == "defer_only":
        args = {"defer_topics": [{"topic": "headcount", "evidence": {
            "message_id": "u1", "quote": req.current_message.text}}]}
    parsed = UpdateEventConditionsInput.model_validate(args)
    result = update_event_conditions(req.draft, parsed, current_message=req.current_message)
    if mode == "unchanged":
        result = update_event_conditions(result.draft, parsed, current_message=req.current_message)
    assert condition_progress("c1", result) is None


@pytest.mark.parametrize("field,value,status,expected", [
    ("headcount", 60, "tentative", "예상 인원 반영했어요"),
    ("fee_per_person", 0, "specified", "참가비 반영했어요"),
    ("fee_per_person", 45000, "specified", "참가비 반영했어요"),
    ("fee_per_person", None, "specified", "참가비 반영했어요"),
    ("event_type", "WELCOME", "specified", "행사 종류 반영했어요"),
    # 값과 잠정 여부는 문구가 아니라 초안 payload로 보존한다(#302).
    ("location", "가평", "specified", "장소 반영했어요"),
    ("title", "봄 MT", "specified", "행사 이름 반영했어요"),
    # 시작일·종료일은 패널의 「일정」 한 칸이라 문구도 「일정」으로 적는다(#300).
    ("start_date", "2026-05-10", "specified", "일정 반영했어요"),
])
def test_condition_payload_preserves_value_meaning(field, value, status, expected):
    req = request()
    args = change_call(req, field, value)["args"]
    change = args["changes"][0]
    change["status"] = status
    if value is None:
        args["changes"] = [dict(op="CLEAR", field=field, evidence=change["evidence"])]
    result = update_event_conditions(req.draft, UpdateEventConditionsInput.model_validate(args),
                                     current_message=req.current_message)
    event = condition_progress("c1", result)
    assert event.text == expected
    assert event.condition_draft == result.draft
    assert getattr(event.condition_draft.conditions, field) == getattr(result.draft.conditions, field)


def test_search_then_guessed_change_does_not_claim_change():
    req = request("작년 봄 MT 참가비로 하자")
    port = Recorder()
    result = run_turn(req, [search_call(), change_call(req, "fee_per_person", 30000)], progress=port,
                      search=lookup(Port((chunk("report", "참가비 45,000원"),))))
    assert result.executions[-1].result.status == "rejected"
    # 거절된 조건 변경은 성공 대신 skipped만 보내 화면이 진행 중 줄을 지우게 한다.
    assert [(e.kind, e.status) for e in port.events] == [
        ("search_started", "running"), ("search_finished", "completed"), ("condition_applied", "skipped")]
    assert port.events[1].text == "참고할 기록을 찾았어요"


@pytest.mark.parametrize("status,expected_status,text", [
    # 자료 없음은 정상 종료라 실패가 아니고, 찾았다는 체크도 아니다(#300).
    ("not_found", "empty", "맞는 기록이 없었어요"),
    ("failed", "failed", "기록을 검색하지 못했어요"),
])
def test_search_empty_and_failure_are_distinct(status, expected_status, text):
    port = Recorder()

    async def search(*args):
        assert port.events[-1].kind == "search_started"
        return (RecordLookupResult(status=status, query="기록", result=RecordSearchResult(not_found=("기록",)))
                if status == "not_found" else RecordLookupResult(status=status, reason="실패"))

    run_turn(request(), [search_call()], progress=port, search=search)
    assert port.events[-1].status == expected_status
    assert port.events[-1].text == text


def test_invalid_search_does_not_start_and_repeated_search_has_distinct_ids():
    port = Recorder()
    search = lookup(Port())
    run_turn(request(), [search_call(query="")], progress=port, search=search)
    assert not port.events
    run_turn(request(), [search_call("s1"), search_call("s2")], progress=port, search=search)
    assert [e.operation_id for e in port.events] == ["s1", "s1", "s2", "s2"]


def test_change_then_generate_and_duplicate_generate_only_report_one_generation():
    req = request("60명으로 바꾸고 초안 만들어줘")
    port = Recorder()
    model = Model()
    result = run_turn(req, [change_call(req, "headcount", 60), gen_call(req, id="g1"), gen_call(req, id="g2")],
                      progress=port, model=model)
    assert [e.kind for e in port.events] == ["condition_applied", "generation_started", "generation_finished"]
    assert [e.operation_id for e in port.events[1:]] == ["g1", "g1"]
    assert port.events[-1].text == f"초안 {len(result.generation_result.preview.steps)}단계를 만들었어요"
    assert len(model.calls) == 1


def test_blocked_chat_generation_has_no_start():
    req = request("초안 만들어줘")
    port = Recorder()
    result = run_turn(req, [gen_call(req, offer_id="stale")], progress=port)
    assert result.generation_result.status == "needs_clarification"
    assert not port.events


def test_button_success_failure_block_and_reuse(monkeypatch):
    port = Recorder()
    model = Model()
    monkeypatch.setattr(workflow, "run_plan_generation", partial(run_plan_generation, invoke=model))
    req = button(public_request())
    result = asyncio.run(ai.generate_planning_preview(req, progress=port))
    assert [e.status for e in port.events] == ["running", "completed"]
    assert {e.operation_id for e in port.events} == {req.request_id}
    port.events.clear()
    again = req.model_copy(update={"resume_state": result.next_state})
    asyncio.run(ai.generate_planning_preview(again, progress=port))
    blocked = button(public_request(draft=ai.PlanningDraft()))
    asyncio.run(ai.generate_planning_preview(blocked, progress=port))
    assert not port.events and len(model.calls) == 1
    monkeypatch.setattr(workflow, "run_plan_generation", partial(run_plan_generation, invoke=Model(ai.AITimeoutError("timeout"))))
    failed = asyncio.run(ai.generate_planning_preview(req, progress=port))
    assert failed.view.generation_result.status == "failed"
    assert [e.status for e in port.events] == ["running", "failed"]
    assert port.events[-1].text == "초안을 만들지 못했어요"


def test_mismatched_generation_result_is_not_announced_as_success(monkeypatch):
    port = Recorder()

    async def wrong_basis(req):
        assert port.events[-1].kind == "generation_started"
        result = await run_plan_generation(req, invoke=Model())
        wrong = result.preview.model_copy(update={"basis_draft": ai.PlanningDraft()})
        return result.model_copy(update={"preview": wrong})

    monkeypatch.setattr(workflow, "run_plan_generation", wrong_basis)
    result = asyncio.run(ai.generate_planning_preview(button(public_request()), progress=port))
    assert result.view.generation_result.status == "failed"
    assert port.events[-1].status == "failed"


def test_public_result_and_stored_state_equal_with_missing_working_or_broken_port(monkeypatch, caplog):
    # graph가 자동으로 붙이는 무작위 메시지 ID만 고정해 저장 JSON 전체를 비교한다.
    monkeypatch.setattr(nodes, "ToolMessage", partial(ToolMessage, id="tool-result"))
    req = public_request()
    results = []
    for port in [None, Recorder(), Recorder(broken=True)]:
        first = tool("update_event_conditions", {"changes": [dict(op="SET", change=dict(field="headcount", value=50),
            status="tentative", evidence=dict(message_id="u1", quote=req.message.content))]})
        first.id = "assistant-tools"
        scripted(monkeypatch, [first, AIMessage(id="assistant-final", content="50명으로 잡았어요.")])
        results.append(asyncio.run(ai.chat_planning(req, progress=port)).model_dump(mode="json"))
    assert results[0] == results[1] == results[2]
    assert "계획 진행 알림 전달 실패" in caplog.text
    assert "private provider payload" not in caplog.text


def test_rejected_condition_in_graph_does_not_emit_success():
    req = request()
    call = change_call(req, "headcount", 60)
    call["args"]["changes"][0]["evidence"]["quote"] = "없는 발화"
    port = Recorder()
    result = run_turn(req, [call], progress=port)
    assert result.executions[0].result.status == "rejected"
    assert [(e.kind, e.status) for e in port.events] == [("condition_applied", "skipped")]


def test_multiple_fields_and_metadata_only_change():
    req = request()
    args = change_call(req, "headcount", 50)["args"]
    result = update_event_conditions(req.draft, UpdateEventConditionsInput.model_validate(args),
                                     current_message=req.current_message)
    assert condition_progress("c1", result).text == "예상 인원 반영했어요"
    args["changes"].extend(change_call(req, "fee_per_person", 30000)["args"]["changes"])
    result = update_event_conditions(req.draft, UpdateEventConditionsInput.model_validate(args),
                                     current_message=req.current_message)
    # 항목 이름만 적고 값은 payload로 보낸다(#302).
    assert condition_progress("c2", result).text == "예상 인원 · 참가비 반영했어요"


@pytest.mark.parametrize("start,end,expected", [
    ("2026-12-05", "2026-12-06", "일정 반영했어요"),
    ("2026-12-31", "2027-01-02", "일정 반영했어요"),
    ("2026-11-28", "2026-12-01", "일정 반영했어요"),
    ("2026-12-05", "2026-12-05", "일정 반영했어요"),
])
def test_start_and_end_dates_read_as_one_schedule(start, end, expected):
    """시작일·종료일이 함께 바뀌어도 「일정」 한 항목으로 적는다(#300)."""
    req = request()
    args = change_call(req, "start_date", start)["args"]
    args["changes"].extend(change_call(req, "end_date", end)["args"]["changes"])
    args["changes"].extend(change_call(req, "headcount", 40)["args"]["changes"])
    result = update_event_conditions(req.draft, UpdateEventConditionsInput.model_validate(args),
                                     current_message=req.current_message)
    text = condition_progress("c1", result).text
    assert text.count("일정") == 1
    assert text.replace("예상 인원 · ", "").replace(" · 예상 인원", "") == expected


def test_button_port_failure_preserves_result(monkeypatch):
    req = button(public_request())
    monkeypatch.setattr(workflow, "run_plan_generation", partial(run_plan_generation, invoke=Model()))
    baseline = asyncio.run(ai.generate_planning_preview(req))

    async def fixed(*args):
        return baseline.view.generation_result

    monkeypatch.setattr(workflow, "run_plan_generation", fixed)
    for port in [Recorder(), Recorder(broken=True)]:
        result = asyncio.run(ai.generate_planning_preview(req, progress=port))
        assert result == baseline
        assert [e.status for e in port.events] == ["running", "completed"]


def test_progress_contract_rejects_false_completion_and_is_public():
    assert ai.PlanningProgressPort is not None
    with pytest.raises(ValidationError):
        ai.PlanningProgress(operation_id="g1", kind="generation_started", status="completed", text="생성")


@pytest.mark.parametrize("kind,status,ok", [
    ("condition_started", "running", True),
    ("condition_started", "completed", False),  # 시작 알림이 완료를 주장하지 않는다
    ("condition_applied", "skipped", True),     # 거절·같은 값: 진행 중 줄을 지운다
    ("condition_applied", "running", False),
    ("search_finished", "skipped", False),      # 검색은 자료 없음도 결과로 보여 준다
    ("search_finished", "empty", True),         # 자료 없음: 회색 대시로 남긴다(#300)
    ("condition_applied", "empty", False),      # 조건은 결과가 없으면 skipped다
    ("generation_finished", "empty", False),
])
def test_condition_start_and_skip_contract(kind, status, ok):
    make = lambda: ai.PlanningProgress(operation_id="c1", kind=kind, status=status, text="문구")
    if ok:
        make()
    else:
        with pytest.raises(ValidationError):
            make()


def test_progress_cancellation_is_not_swallowed():
    class CancelledPort:
        async def progress(self, event):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(notify(CancelledPort(), started("s1")))


@pytest.mark.parametrize("fields,expected", [
    (["headcount", "start_date", "end_date", "fee_per_person"], "예상 인원 · 일정 · 참가비 반영했어요"),
    (["headcount", "start_date", "end_date", "fee_per_person", "location"], "예상 인원 · 일정 외 2개 반영했어요"),
    (["title", "event_type", "headcount", "fee_per_person", "location"], "행사 이름 · 행사 종류 외 3개 반영했어요"),
])
def test_summary_counts_schedule_once_and_limits_names(fields, expected):
    from app.ai.features.planning.agent.tools import ConditionUpdateResult
    result = ConditionUpdateResult(status="applied", changed_fields=tuple(fields), draft=ai.PlanningDraft())
    assert condition_progress("c1", result).text == expected


@pytest.mark.parametrize("kind,status", [
    ("condition_started", "running"), ("condition_applied", "skipped"),
    ("search_finished", "completed"), ("generation_finished", "completed"),
])
def test_condition_payload_is_for_condition_completion_only(kind, status):
    with pytest.raises(ValidationError, match="조건 초안"):
        ai.PlanningProgress(operation_id="c1", kind=kind, status=status, text="문구",
                            condition_draft=ai.PlanningDraft())
