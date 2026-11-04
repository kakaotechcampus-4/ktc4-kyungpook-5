"""영수증 이미지에서 검토할 지출 행을 추출한다."""

import base64
from functools import cache
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ...contracts import ExtractReceiptRequest, ExtractReceiptResult
from ...llm import ainvoke_structured


@cache
def _system_prompt() -> str:
    return (Path(__file__).parent / "prompts" / "extract_receipt.md").read_text(
        encoding="utf-8"
    )


def _build_messages(request: ExtractReceiptRequest) -> list[BaseMessage]:
    encoded = base64.b64encode(request.image_bytes).decode("ascii")
    data_url = f"data:{request.mime_type};base64,{encoded}"
    return [
        SystemMessage(_system_prompt()),
        HumanMessage(
            content=[
                {"type": "text", "text": f"파일명: {request.file_name}"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        ),
    ]


async def extract_receipt(request: ExtractReceiptRequest) -> ExtractReceiptResult:
    """이미지 한 장을 읽어 검토용 행을 돌려준다.

    영수증이 아니거나 읽을 수 없으면 빈 rows로 표현한다. 모델·네트워크
    오류는 공통 AI 오류로 올려 호출부가 실패와 빈 결과를 구분하게 한다.
    """
    return await ainvoke_structured(_build_messages(request), ExtractReceiptResult)
