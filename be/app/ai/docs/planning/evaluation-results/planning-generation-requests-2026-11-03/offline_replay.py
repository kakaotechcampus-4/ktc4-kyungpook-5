"""실제 모델 대신 응답을 주입해 여러 턴의 동일 거절과 직접 요청 복구를 확인한다."""
import argparse
import asyncio
from functools import partial
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.ai import PlanningChatRequest, chat_planning, generate_planning_preview
from app.ai.features.planning import public_workflow
from app.ai.features.planning.agent import graph as agent_graph, nodes
from app.ai.features.planning.generation.graph import run_plan_generation
from app.ai.scripts import check_planning_generation_requests as check
from app.ai.tests.test_plan_generation_graph import Model


async def replay(fixture):
    rows=[]
    for case_id in check.CASE_IDS[1:]:
        original=check.make_request(fixture,case_id,'chat',f'offline-{case_id}')
        state=original.resume_state
        model=Model()
        use_old_id=True
        async def agent(messages, **kwargs):
            if isinstance(messages[-1],ToolMessage):
                return AIMessage(content='Tool 처리 결과를 확인해 주세요.')
            human=next(m for m in reversed(messages) if isinstance(m,HumanMessage))
            args=dict(quote=human.text)
            if use_old_id:
                args['offer_id']=original.resume_state.payload.generation.offer.id
            return AIMessage(content='',tool_calls=[dict(name=nodes.GENERATE_TOOL_NAME,
                id=f'gen-{human.id}',args=args)])
        with patch.object(agent_graph,'call_agent_model',agent), patch.object(public_workflow,
                'run_plan_generation',partial(run_plan_generation,invoke=model)):
            for number in range(1,5):
                use_old_id=number<=3
                request=PlanningChatRequest(**{**original.model_dump(exclude={'message','resume_state','draft'}),
                    'request_id':f'offline-{case_id}-{number}','resume_state':state,'draft':state.payload.basis_draft,
                    'message':dict(id=f'offline-user-{number}',content=check.DIRECT_REQUEST)})
                before=len(model.calls)
                result=await chat_planning(request)
                rows.append(dict(case_id=case_id,turn=number,offer_id_supplied=use_old_id,
                    status=result.view.generation_result.status,generation_calls=len(model.calls)-before,
                    draft_preserved=result.view.draft==original.draft))
                state=result.next_state
            button=check.make_request(fixture,case_id,'button',f'offline-button-{case_id}')
            before=len(model.calls)
            result=await generate_planning_preview(button)
            rows.append(dict(case_id=case_id,route='button',status=result.view.generation_result.status,
                generation_calls=len(model.calls)-before,history_preserved=result.next_state.payload.history==button.resume_state.payload.history))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    raw=args.fixture.read_bytes()
    report=dict(mode='injected_control_flow',actual_provider_calls=0,
        fixture_sha256=hashlib.sha256(raw).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        rows=asyncio.run(replay(check.validate_fixture(json.loads(raw)))))
    with args.output.open('x') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
    print(json.dumps(report['rows'],ensure_ascii=False))
