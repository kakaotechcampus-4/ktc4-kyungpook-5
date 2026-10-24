"""저장 없는 로컬 FE-AI 테스트 서버. 실서비스 app.main에는 등록하지 않는다.

be/에서 .venv/bin/python -m app.ai.scripts.planning_playground
127.0.0.1:8011에만 바인딩한다. FE Vite의 /__planning-test 프록시로 호출한다.
"""

import asyncio
import json
import time
from functools import partial
from pathlib import Path

from fastapi import FastAPI, HTTPException
from langchain_core.messages import AnyMessage
from pydantic import Field, field_validator, model_validator

from app.ai.config import AISettings
from app.ai.contracts import ContractModel, IndexRecordRequest, NonBlankStr
from app.ai.errors import AIConfigError, AIRetryableError
from app.ai.features.planning.agent.graph import run_planning_agent_turn
from app.ai.features.planning.agent.nodes import PROMPT_VERSION
from app.ai.features.planning.agent.schemas import PlanningAgentTurnInput, validate_planning_history
from app.ai.features.planning.agent.record_tool import search_past_events
from app.ai.features.planning.agent.state import PlanningDraft
from app.ai.features.planning.agent.generation_tools import latest_reference_facts, plan_messages
from app.ai.features.planning.generation.entrypoints import ButtonPlanGenerationRequest, run_button_plan_generation
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.features.planning.generation.schemas import PlanningGenerationState, valid_timezone
from app.ai.features.planning.schemas import CalendarDate
from app.ai.features.planning.turn_flow import process_planning_turn
from app.ai.features.planning.turn_schemas import PlanningTurnInput
from app.ai.features.retrieval.indexing import index_record_chunks
from app.ai.features.retrieval.memory_port import InMemoryRecordSearch, StoredRecord
from app.core.enums import RecordCategory

app = FastAPI(title="Planning local playground", docs_url=None, redoc_url=None)
memory = InMemoryRecordSearch()
fixture_count = 0
lock = asyncio.Lock()


class PlaygroundButtonRequest(ContractModel):
    request_id: NonBlankStr
    draft: PlanningDraft
    generation: PlanningGenerationState = Field(default_factory=PlanningGenerationState)
    history: tuple[AnyMessage, ...] = Field(default=(), max_length=60)
    reference_date: CalendarDate
    timezone: NonBlankStr = "Asia/Seoul"
    use_current_conditions: bool = False

    _timezone = field_validator("timezone")(valid_timezone)

    @model_validator(mode="after")
    def _history(self):
        validate_planning_history(self.history)
        return self


def safe_failure(error):
    # 공급자 예외 원문에는 주소·인증 정보가 있을 수 있으므로 브라우저에는 분류만 전달한다.
    if isinstance(error, AIConfigError):
        return HTTPException(503, "AI 서버 설정을 확인해 주세요.")
    if isinstance(error, AIRetryableError):
        return HTTPException(503, "AI 호출에 실패했어요. 현재 조건은 유지됩니다. 다시 시도해 주세요.")
    return HTTPException(500, "처리 결과를 조립하지 못했어요. 현재 조건은 유지됩니다.")


@app.get("/__planning-test/health")
async def health():
    settings = AISettings()
    return {"model": settings.model, "fixture_count": fixture_count, "storage": "memory-only",
            "agent_version": PROMPT_VERSION, "record_search": True, "plan_generation": True}


@app.post("/__planning-test/agent/turn")
async def agent_turn(request: PlanningAgentTurnInput):
    # 새 화면은 초안·Tool 이력을 그대로 왕복한다. 서버에 대화 상태를 보관하지 않는다.
    async with lock:
        started = time.perf_counter()
        try:
            # 요청마다 현재 메모리를 주입한다. 샘플 색인으로 저장소가 교체돼도 이전 port에 묶이지 않는다.
            result = await run_planning_agent_turn(request,
                search=partial(search_past_events, club_id="clb_keunnamu", port=memory), generate=run_plan_generation)
        except Exception as error:
            raise safe_failure(error) from None
        return {"result": result.model_dump(mode="json"),
                "elapsed_ms": round((time.perf_counter() - started) * 1000), "fixture_count": fixture_count}


@app.post("/__planning-test/agent/generate")
async def button_generate(request: PlaygroundButtonRequest):
    # 클릭을 채팅으로 위장하지 않는다. 검증한 실제 이력에서 생성 문맥·최근 기록 사실만 준비한다.
    async with lock:
        started = time.perf_counter()
        try:
            result = await run_button_plan_generation(ButtonPlanGenerationRequest(
                request_id=request.request_id, draft=request.draft, generation=request.generation,
                messages=plan_messages(request.history), reference_facts=latest_reference_facts(request.history),
                reference_date=request.reference_date, timezone=request.timezone,
                use_current_conditions=request.use_current_conditions), generate=run_plan_generation)
        except Exception as error:
            raise safe_failure(error) from None
        return {"result": result.model_dump(mode="json"), "source": "button",
                "elapsed_ms": round((time.perf_counter() - started) * 1000), "fixture_count": fixture_count}


@app.post("/__planning-test/records")
async def load_records():
    global memory, fixture_count
    async with lock:
        if fixture_count:
            return {"fixture_count": fixture_count}
        # 실제 DB 대신 기존 합성 기록을 실제 임베딩해 메모리에만 넣는다.
        candidate = InMemoryRecordSearch()
        paths = sorted((Path(__file__).resolve().parents[1] / "tests/fixtures/records").glob("*.json"))
        try:
            for path in paths:
                data = json.loads(path.read_text()); record = data["record"]
                indexed = await index_record_chunks(IndexRecordRequest(
                    record_id=record["id"], file_name=record["file_name"], file_type=record["file_type"],
                    blocks=data["parse_result"]["blocks"]))
                candidate.add(StoredRecord(record_id=record["id"], club_id=record["club_id"],
                    file_name=record["file_name"], category=RecordCategory(record["category"]),
                    event_id=record["event_id"]), indexed.chunks)
        except Exception as error:
            raise safe_failure(error) from None
        memory, fixture_count = candidate, len(paths)
        return {"fixture_count": fixture_count}


@app.post("/__planning-test/turn")
async def turn(request: PlanningTurnInput):
    # 요청의 조건·문맥은 브라우저 임시 상태다. DB 권한·영속 저장을 검증하는 API가 아니다.
    if request.club_id != "clb_keunnamu":
        raise HTTPException(400, "테스트 동아리만 사용할 수 있습니다.")
    async with lock:
        started = time.perf_counter()
        try:
            result = await process_planning_turn(request, port=memory)
        except Exception as error:
            raise safe_failure(error) from None
        return {"result": result.model_dump(mode="json"),
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                "fixture_count": fixture_count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8011)
