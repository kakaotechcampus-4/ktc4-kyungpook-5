"""운영 중 입력을 확인 질문 또는 읽기 전용 제안으로 정리한다."""
import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from ...errors import AIInvalidResponseError
from ...llm import ainvoke_structured
from .schemas import OperationalSituationRequest, OperationalSituationResult


_PROMPT = (Path(__file__).parent / 'prompts' / 'situation.md').read_text(encoding='utf-8')


async def respond_operational_situation(request: OperationalSituationRequest) -> OperationalSituationResult:
    """저장·권한·실행 없이 확인 질문 또는 제안만 반환한다."""
    data = request.model_dump(mode='json')
    messages = [SystemMessage(_PROMPT), HumanMessage(json.dumps(data, ensure_ascii=False))]
    result = await ainvoke_structured(messages, OperationalSituationResult)
    try:
        result = OperationalSituationResult.model_validate(result)
    except ValidationError as error:
        raise AIInvalidResponseError('운영 상황 응답 형식이 올바르지 않습니다') from error
    if request.answer is not None and result.status != 'suggestion':
        raise AIInvalidResponseError('답변 후 확인 질문을 반복할 수 없습니다')
    return result
