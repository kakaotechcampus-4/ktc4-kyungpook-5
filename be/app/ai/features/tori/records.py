"""토리 질문의 근거를 검색된 청크에서만 정리한다."""
import re
from datetime import date
from typing import Literal

from pydantic import Field

from ...contracts import ContractModel, NonBlankStr, RecordConflict, RecordFact
from ...ports import RetrievedChunk
from ..retrieval.nodes import assess_chunks
from ..retrieval.schemas import RecordSearchRequest


class ToriRecordAnswerRequest(ContractModel):
    question: NonBlankStr = Field(max_length=4000)
    today: date
    chunks: tuple[RetrievedChunk, ...] = Field(max_length=50)


class ToriRecordAnswerResult(ContractModel):
    status: Literal['answered', 'partial', 'no_evidence']
    facts: tuple[RecordFact, ...] = ()
    conflicts: tuple[RecordConflict, ...] = ()
    not_found: tuple[NonBlankStr, ...] = ()


# shortcut: 원문의 숫자 표기만 비교한다. 환산·계산은 검증 가능한 계산기 도입 시 확장한다.
_NUMBER = re.compile(r'(?<![\d.])\d[\d,]*(?:\.\d+)?(?![\d.])\s*(?:조|억|만|천|백|십)?\s*(?:원|명|개|건|%|년|월|일)?')
_YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?=년|[_\W]|$)')


def _numbers(text: str) -> set[str]:
    return {re.sub(r'[,\s]', '', value) for value in _NUMBER.findall(text)}


def _supported(fact: RecordFact, chunks: tuple[RetrievedChunk, ...], years: set[str]) -> bool:
    cited = [chunk for chunk in chunks if chunk.source in fact.sources]
    evidence = '\n'.join(f'{chunk.text} {chunk.source.file_name} {chunk.source.location.label}' for chunk in cited)
    text_numbers = _numbers('\n'.join(chunk.text for chunk in cited))
    evidence_years = set(_YEAR.findall(evidence))
    # 문서명 연도만 예외로 허용하고 금액·인원은 본문에서 확인한다.
    claimed = {number for number in _numbers(fact.content)
               if number.removesuffix('년') not in evidence_years}
    return bool(cited) and not (claimed - text_numbers) and (not years or bool(years & evidence_years))


async def answer_tori_records(request: ToriRecordAnswerRequest) -> ToriRecordAnswerResult:
    if not request.chunks:
        return ToriRecordAnswerResult(status='no_evidence', not_found=(request.question,))
    # 이 호출은 검색을 다시 하지 않는다. BE가 승인한 청크 외의 출처는 생성할 수 없다.
    search = RecordSearchRequest(club_id='provided', query=request.question, today=request.today)
    result = await assess_chunks(search, request.chunks)
    years = set(_YEAR.findall(request.question))
    facts = tuple(fact for fact in result.facts if _supported(fact, request.chunks, years))
    conflicts = tuple(conflict for conflict in result.conflicts
                      if all(_supported(value, request.chunks, years) for value in conflict.values)
                      and _numbers(conflict.description) <= _numbers(' '.join(v.content for v in conflict.values)))
    removed = len(facts) != len(result.facts) or len(conflicts) != len(result.conflicts)
    not_found = result.not_found + (('자료의 일부 내용을 확인하지 못했어요.',) if removed else ())
    status = 'partial' if (facts or conflicts) and not_found else 'answered' if (facts or conflicts) else 'no_evidence'
    return ToriRecordAnswerResult(status=status, facts=facts, conflicts=conflicts,
                                  not_found=not_found or ((request.question,) if status == 'no_evidence' else ()))
