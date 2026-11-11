"""실제 회의 판단 기록을 Jev로 다시 판단하는 스크립트가 luna가 본 입력 글을 그대로 다시 만드는지 검증한다(#245).

운영 BE가 저장한 judge_input으로 같은 글을 만들어야 luna 판단과 견줄 수 있다. 실제 Jev는 부르지 않는다.
"""

import json
from argparse import Namespace

import httpx

from app.ai.features.meeting.context import build_judge_input
from app.ai.features.meeting.schemas import JudgeUtteranceRequest
from app.ai.scripts.check_jev_judge import JevClient
from app.ai.scripts.rejudge_meeting_decisions import compare, jev_inputs, run


def _utterance(seq: int, text: str) -> dict:
    return {
        "utterance_id": f"seg_{seq}", "seq": seq, "version": 1, "text": text,
        "started_at": f"2026-11-03T05:00:{seq:02d}+00:00", "ended_at": f"2026-11-03T05:00:{seq:02d}.500000+00:00",
    }


def _decision(id_: str, route: str, text: str, judge_input: bool = True) -> dict:
    # 운영 BE(context_service.decide_live_meeting_segment)가 저장하는 judge_input 모양이다
    payload = {
        "meeting_id": "mtg_1", "club_id": "clb_1",
        "utterance": _utterance(3, text), "context": [_utterance(1, "MT 얘기부터 할게요"), _utterance(2, "숙소부터요")],
    }
    return {
        "id": id_, "meeting_id": "mtg_1", "status": "SUCCEEDED", "route": route, "question": None,
        "policy_version": "meeting-judge-v6", "judge_ms": 1500, "created_at": "2026-11-03T05:00:04+00:00",
        "judge_input": payload if judge_input else None,
    }


def test_rebuilds_the_same_input_text_luna_saw():
    decision = _decision("cdc_1", "RAG", "작년엔 숙소비 얼마였지?")
    [(_, state)], skipped = jev_inputs([decision])
    assert state == build_judge_input(JudgeUtteranceRequest.model_validate(decision["judge_input"]))
    assert "[방금 발화]\n작년엔 숙소비 얼마였지?" in state and "숙소부터요" in state
    assert skipped == []


def test_skips_decisions_without_judge_input():
    # #241 전 기록과 Discord 판단은 그때 입력을 다시 만들 수 없다
    items, skipped = jev_inputs([_decision("cdc_old", "NONE", "네", judge_input=False)])
    assert items == [] and skipped == [{"id": "cdc_old", "reason": "judge_input 없음"}]


def test_compare_leaves_luna_failures_out_of_agreement():
    records = [
        {"luna_route": "RAG", "jev_lookup": True},
        {"luna_route": "RAG", "jev_lookup": False},
        {"luna_route": "NONE", "jev_lookup": True},
        {"luna_route": "NONE", "jev_lookup": False},
        {"luna_route": "NONE", "jev_lookup": False},
        {"luna_route": "ERROR", "jev_lookup": True},
    ]
    assert compare(records) == {
        "compared": 5, "agree": "3 / 5",
        "luna_rag_jev_lookup": 1, "luna_rag_jev_no": 1, "luna_none_jev_lookup": 1, "luna_none_jev_no": 2,
        "luna_error": 1,
    }


def test_run_lists_disagreements_with_luna(tmp_path):
    path = tmp_path / "decisions.jsonl"
    rows = [_decision("cdc_1", "RAG", "작년엔 숙소비 얼마였지?"), _decision("cdc_2", "NONE", "아 다리 아파"),
            _decision("cdc_3", "NONE", "네", judge_input=False)]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))

    def handler(request: httpx.Request) -> httpx.Response:
        state = json.loads(request.content)["state"]
        p = 0.9 if "숙소비" in state.split("[방금 발화]")[-1] else 0.5
        return httpx.Response(200, json={"model": "typesafe/jev-1.14-20261014",
                                         "answers": {"record_lookup": {"noul": p}}, "usage": {"prompt_tokens": 300}})

    client = JevClient("https://mlapi.example/abc", "k", "typesafe/jev-1.14", timeout=1)
    client.http = httpx.Client(transport=httpx.MockTransport(handler), timeout=1)
    report = run(Namespace(decisions=path, repeat=1, threshold=0.35), client, {"commit": "x"})

    assert report["input"]["rejudged"] == 2 and report["input"]["skipped"] == 1
    assert report["comparison"]["agree"] == "1 / 2"
    assert [(r["id"], r["jev_lookup"]) for r in report["records"]] == [("cdc_1", True), ("cdc_2", True)]
    assert report["latency"]["luna_judge_ms_production"]["n"] == 2
