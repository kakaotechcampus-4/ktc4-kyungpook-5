"""토리 질문의 근거를 검색된 청크에서만 정리한다."""
import re
from datetime import date
from typing import Literal

from pydantic import Field

from ...contracts import ContractModel, NonBlankStr, RecordConflict, RecordFact
from ...ports import RetrievedChunk
from ..retrieval.nodes import assess_chunks
from ..retrieval.schemas import EvidenceAssessment, EvidenceItem, RecordSearchRequest


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
_NUMBER = re.compile(r'(?<![\d.])(?:[+\-−]|마이너스|음수|플러스)?\s*\d[\d,]*(?:\.\d+)?(?![\d.])\s*(?:조|억|만|천|백|십)?\s*(?:원|명|개|건|%|년|월|일)?')
_KOREAN_NUMBER = re.compile(r'(?<![\d.])(?:[+\-−]|마이너스|음수|플러스)?\s*(?:[영공일이삼사오육칠팔구십백천만억조]+|(?:스물|서른|마흔|쉰|예순|일흔|여든|아흔)(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉)?|스무|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:원|명|개|건|%|퍼센트|년|월|일)')
_AMBIGUOUS_AMOUNT = re.compile(r'\(\s*(?:\d[\d,]*(?:\.\d+)?|[영공일이삼사오육칠팔구십백천만억조]+)\s*(?:조|억|만|천|백|십)?\s*원?\s*\)')
_YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\s*(?:원|명|개|건|%|월|일|만원|억원))(?=년|(?:에서|으로|부터|까지|에는|의|에|은|는|이|가|도|과|와)(?![가-힣])|[_\W]|$)')


def _numbers(text: str) -> set[str]:
    text = _AMBIGUOUS_AMOUNT.sub('', text)
    values = list(_NUMBER.findall(text))
    for match in _KOREAN_NUMBER.finditer(text):
        # 아라비아 숫자와 띄어 쓴 단위(예: 10 만원)는 별도 한글 수사가 아니다.
        before = text[:match.start()].rstrip()
        if before and (before[-1].isdigit() or before[-1] == '.'):
            continue
        value = match.group().strip()
        start = match.end() - len(match.group().lstrip())
        if (start and '가' <= text[start - 1] <= '힣'
                and re.fullmatch(r'[일이삼사오육칠팔구](?:명|원)', value)
                and not before.endswith(('은', '는', '이', '가', '을', '를', '참가자', '참석자', '인원'))):
            continue
        values.append(value)
    return {re.sub(r'[,\s]', '', value).replace('−', '-').replace('마이너스', '-').replace('음수', '-').replace('플러스', '+').removeprefix('+')
            for value in values}


def _supported(item: EvidenceItem, chunks: tuple[RetrievedChunk, ...], years: set[str]) -> bool:
    if _AMBIGUOUS_AMOUNT.search(item.content):
        return False
    cited = [chunks[int(key[1:]) - 1] for key in item.chunk_ids]
    evidence = '\n'.join(f'{chunk.text} {chunk.source.file_name} {chunk.source.location.label}' for chunk in cited)
    text_numbers = _numbers('\n'.join(chunk.text for chunk in cited))
    evidence_years = set(_YEAR.findall(evidence))
    # 문서명 연도만 예외로 허용하고 금액·인원은 본문에서 확인한다.
    claimed = {number for number in _numbers(item.content)
               if number.removesuffix('년') not in evidence_years}
    return bool(cited) and not (claimed - text_numbers) and (not years or bool(years & evidence_years))


async def answer_tori_records(request: ToriRecordAnswerRequest) -> ToriRecordAnswerResult:
    if not request.chunks:
        return ToriRecordAnswerResult(status='no_evidence', not_found=(request.question,))
    # 이 호출은 검색을 다시 하지 않는다. BE가 승인한 청크 외의 출처는 생성할 수 없다.
    search = RecordSearchRequest(club_id='provided', query=request.question, today=request.today)
    years = set(_YEAR.findall(request.question))

    def filter_evidence(assessment: EvidenceAssessment) -> EvidenceAssessment:
        facts = [item for item in assessment.facts if _supported(item, request.chunks, years)]
        conflicts = [conflict for conflict in assessment.conflicts
                     if not _AMBIGUOUS_AMOUNT.search(conflict.description)
                     and all(_supported(value, request.chunks, years) for value in conflict.values)
                     and _numbers(conflict.description) <= _numbers(' '.join(v.content for v in conflict.values))]
        removed = len(facts) != len(assessment.facts) or len(conflicts) != len(assessment.conflicts)
        not_found = list(assessment.not_found)
        if removed:
            not_found.append('자료의 일부 내용을 확인하지 못했어요.')
        return assessment.model_copy(update={'facts': facts, 'conflicts': conflicts, 'not_found': not_found})

    result = await assess_chunks(search, request.chunks, filter_assessment=filter_evidence)
    status = ('partial' if (result.facts or result.conflicts) and result.not_found
              else 'answered' if (result.facts or result.conflicts) else 'no_evidence')
    return ToriRecordAnswerResult(status=status, facts=result.facts, conflicts=result.conflicts,
                                  not_found=result.not_found)
