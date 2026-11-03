"""영수증 이미지에서 지출 내역을 읽는다.

전용 OCR API(네이버·구글 등) 대신, 비전 입력이 되는 범용 채팅 모델(gpt-5.6-luna)을
그대로 쓴다 — 한국어 인식률과 비용을 함께 따져본 팀 논의 결과다(#112).
"""

import base64
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from ...contracts import ExtractReceiptRequest, ExtractReceiptResult
from ...llm import ainvoke_structured

_PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_receipt.md"


def _system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").removesuffix("\n")


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
    """영수증 이미지 한 장을 읽어 지출 행을 돌려준다.

    영수증이 아니거나 읽을 수 없는 이미지는 빈 rows로 돌아온다(예외가 아니다).
    모델 호출 실패는 ainvoke_structured가 AI 오류 타입으로 바꿔 올린다.
    """
    messages = _build_messages(request)
    return await ainvoke_structured(messages, ExtractReceiptResult)
