from typing import Annotated, Literal
from pydantic import StringConstraints

from app.schemas.common import CamelModel, PageMeta, UtcDateTime
from app.schemas.events import ActionOut


class OperationCaseIn(CamelModel):
    client_request_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    situation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class OperationResult(CamelModel):
    summary: str
    suggestions: list[str]


class OperationError(CamelModel):
    code: str
    message: str


class OperationCaseOut(CamelModel):
    id: str
    event_id: str
    client_request_id: str
    situation: str
    question_status: Literal['PENDING', 'PROCESSING', 'NEEDS_ANSWER', 'NO_QUESTION', 'FAILED']
    action: ActionOut | None
    result_status: Literal['NOT_REQUESTED', 'PROCESSING', 'READY', 'FAILED']
    result: OperationResult | None
    error: OperationError | None
    created_at: UtcDateTime
    modified_at: UtcDateTime


class OperationCaseList(CamelModel):
    data: list[OperationCaseOut]
    meta: PageMeta
