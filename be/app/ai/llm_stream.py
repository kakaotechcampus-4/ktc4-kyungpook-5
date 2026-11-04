"""Responses API 조각의 표시와 저장 형태. 공급자 호출·DB에는 의존하지 않는다."""
from copy import deepcopy
from collections.abc import Awaitable, Callable

from langchain_core.messages import AIMessage, AIMessageChunk, message_chunk_to_message

TextCallback = Callable[[str], Awaitable[None]]
ResetCallback = Callable[[], Awaitable[None]]


def final_answer_text(message: AIMessage) -> str:
    """명시된 최종 답변만 표시하되 phase 없는 기존 메시지는 그대로 읽는다."""
    blocks = message.content if isinstance(message.content, list) else []
    texts = [b for b in blocks if isinstance(b, dict) and b.get('type') == 'text']
    if any(b.get('phase') is not None for b in texts):
        return ''.join(b.get('text', '') for b in texts if b.get('phase') == 'final_answer')
    return message.text


def assembled_message(chunk: AIMessageChunk) -> AIMessage:
    message = message_chunk_to_message(chunk)
    content = deepcopy(message.content)
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block.pop('index', None)
            if block.get('type') == 'text':
                block.setdefault('annotations', [])
            if block.get('type') == 'reasoning':
                for part in block.get('summary', []):
                    if isinstance(part, dict):
                        part.pop('index', None)
    return message.model_copy(update={'content': content})


class ReplyStream:
    """UI에 전달한 접두부를 관리한다. Tool이 있으면 이번 모델 호출의 답변은 숨긴다."""

    def __init__(self, on_text: TextCallback, on_reset: ResetCallback):
        self.on_text = on_text
        self.on_reset = on_reset
        self.sent = ''
        self.has_tools = False
        self.buffered = False

    async def reset(self):
        if self.sent:
            await self.on_reset()
            self.sent = ''

    async def accept(self, combined: AIMessageChunk):
        self.has_tools |= bool(combined.tool_call_chunks or combined.tool_calls or combined.invalid_tool_calls)
        if self.has_tools:
            await self.reset()
            return
        blocks = combined.content if isinstance(combined.content, list) else []
        texts = [b for b in blocks if isinstance(b, dict) and b.get('type') == 'text']
        # 뒤늦게 분류되는 앞 블록 때문에 표시 순서가 바뀔 수 있으면 끝까지 모은다.
        if any(b.get('text') and b.get('phase') not in {'final_answer', 'commentary'} for b in texts):
            self.buffered = True
        if self.buffered:
            return
        answer = ''.join(b.get('text', '') for b in texts if b.get('phase') == 'final_answer')
        if not answer.startswith(self.sent):
            self.buffered = True
            return
        if answer[len(self.sent):]:
            await self.on_text(answer[len(self.sent):])
            self.sent = answer

    async def finish(self, response: AIMessage):
        if self.has_tools or response.tool_calls:
            await self.reset()
            return
        answer = final_answer_text(response)
        if not answer.startswith(self.sent):
            await self.reset()
        if answer[len(self.sent):]:
            await self.on_text(answer[len(self.sent):])
            self.sent = answer
