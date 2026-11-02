"""토리 질문의 근거를 검색된 청크에서만 정리한다."""
import json
import re
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, StringConstraints

from ...contracts import ContractModel, NonBlankStr, RecordConflict, RecordFact
from ...ports import RetrievedChunk
from ...errors import AIInvalidResponseError
from ...llm import ainvoke_structured
from ..retrieval.nodes import assess_chunks
from ..retrieval.schemas import EvidenceAssessment, EvidenceItem, RecordSearchRequest


QuestionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
OptionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ToriRecordAnswerRequest(ContractModel):
    question: NonBlankStr = Field(max_length=4000)
    today: date
    follow_up: NonBlankStr | None = Field(default=None, max_length=4000)
    clarification_allowed: bool = True
    clarification_question: QuestionText | None = None
    clarification_options: tuple[OptionText, ...] = Field(default=(), max_length=3)
    chunks: tuple[RetrievedChunk, ...] = Field(max_length=50)


class ToriRecordAnswerResult(ContractModel):
    status: Literal['answered', 'partial', 'no_evidence', 'clarification']
    facts: tuple[RecordFact, ...] = ()
    conflicts: tuple[RecordConflict, ...] = ()
    not_found: tuple[NonBlankStr, ...] = ()
    clarification_question: QuestionText | None = None
    clarification_options: tuple[OptionText, ...] = Field(default=(), max_length=3)


class ToriOption(EvidenceItem):
    content: OptionText


class ToriAssessment(EvidenceAssessment):
    facts: list[EvidenceItem] = Field(max_length=5)
    not_found: list[str] = Field(max_length=2)
    clarification_question: QuestionText | None
    clarification_options: list[ToriOption] = Field(max_length=3)


_PROMPT = Path(__file__).with_name('records_prompt.md').read_text(encoding='utf-8')


# shortcut: 원문의 숫자 표기만 비교한다. 환산·계산은 검증 가능한 계산기 도입 시 확장한다.
_NUMBER = re.compile(r'(?<![\d.])(?:₩\s*)?(?:[+\-−]|마이너스|음수|플러스)?\s*(?:₩\s*)?\d[\d,]*(?:\.\d+)?(?![\d.])\s*(?:조|억|만|천|백|십)?\s*(?:원|명|개|건|%|년|월|일)?')
_KOREAN_NUMBER = re.compile(r'(?<![\d.])(?:[+\-−]|마이너스|음수|플러스)?\s*(?:[영공일이삼사오육칠팔구십백천만억조]+|(?:스물|서른|마흔|쉰|예순|일흔|여든|아흔)(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉)?|스무|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:원|명|개|건|%|퍼센트|년|월|일)')
_AMBIGUOUS_AMOUNT = re.compile(r'\(\s*(?:₩\s*)?(?:\d[\d,]*(?:\.\d+)?|[영공일이삼사오육칠팔구십백천만억조]+)\s*(?:조|억|만|천|백|십)?\s*원?\s*\)')
_YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\s*(?:원|명|개|건|%|월|일|만원|억원))(?=년|(?:에서|으로|부터|까지|에는|의|에|은|는|이|가|도|과|와)(?![가-힣])|[_\W]|$)')


def _numbers(text: str) -> set[str]:
    # 일반 단어 '행사명'은 한글 수사 '사명'과 겹치므로 먼저 제외한다.
    text = _AMBIGUOUS_AMOUNT.sub('', text).replace('행사명', '')
    values = list(_NUMBER.findall(text))
    for match in _KOREAN_NUMBER.finditer(text):
        # 아라비아 숫자와 띄어 쓴 단위(예: 10 만원)는 별도 한글 수사가 아니다.
        before = text[:match.start()].rstrip()
        if before and (before[-1].isdigit() or before[-1] == '.'):
            continue
        values.append(match.group().strip())
    normalized = set()
    for value in values:
        value = re.sub(r'[,\s]', '', value).replace('−', '-').replace('마이너스', '-').replace('음수', '-').replace('플러스', '+')
        won = '₩' in value
        value = value.replace('₩', '').removeprefix('+')
        normalized.add(value + ('원' if won and not value.endswith('원') else ''))
    return normalized


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
    years = set(_YEAR.findall(request.question + ' ' + (request.follow_up or '')))
    clarification = None

    def validate_options(options: list[EvidenceItem]) -> tuple[str, ...]:
        valid = []
        valid_ids = {f'c{i}' for i in range(1, len(request.chunks) + 1)}
        for option in options:
            if option.content == '전체 요약' and not option.chunk_ids:
                valid.append(option.content)
                continue
            if not option.chunk_ids or any(key not in valid_ids for key in option.chunk_ids):
                raise AIInvalidResponseError('범위 선택지의 자료 번호가 올바르지 않습니다')
            texts = ' '.join(request.chunks[int(key[1:]) - 1].text + ' ' +
                             request.chunks[int(key[1:]) - 1].source.file_name for key in option.chunk_ids)
            normalized = re.sub(r'[^0-9가-힣a-z]', '', option.content.lower())
            year_label = re.fullmatch(r'((?:19|20)\d{2})년(?:의)?(?:행사)?(?:예산)?', normalized)
            matches_year = bool(year_label and year_label.group(1) in _YEAR.findall(texts))
            if not normalized or (not matches_year and normalized not in re.sub(r'[^0-9가-힣a-z]', '', texts.lower())):
                raise AIInvalidResponseError('범위 선택지가 인용 자료에 없습니다')
            valid.append(option.content)
        if not 2 <= len(set(valid)) == len(valid) <= 3:
            raise AIInvalidResponseError('범위 선택지는 두 개 또는 세 개여야 합니다')
        return tuple(valid)

    async def invoke(messages, _schema):
        nonlocal clarification
        can_ask = request.clarification_allowed and request.follow_up is None
        extra = json.dumps({'후속 답': request.follow_up, '앞선 범위 질문': request.clarification_question,
                            '앞선 선택지': request.clarification_options, '범위 질문 허용': can_ask},
                           ensure_ascii=False)
        model_messages = [SystemMessage(_PROMPT), HumanMessage(messages[-1].content + '\n\n' + extra)]
        for attempt in range(2):
            assessment = await ainvoke_structured(model_messages, ToriAssessment)
            try:
                if assessment.clarification_question:
                    if not can_ask or assessment.facts or assessment.conflicts:
                        raise AIInvalidResponseError('허용되지 않은 범위 질문입니다')
                    options = validate_options(assessment.clarification_options)
                    clarification = (assessment.clarification_question, options)
                    return EvidenceAssessment(sufficient=True, retry_queries=[], facts=[], conflicts=[],
                                              not_found=[request.question])
                if assessment.clarification_options:
                    raise AIInvalidResponseError('범위 질문 없이 선택지를 반환했습니다')
                return assessment
            except AIInvalidResponseError:
                if attempt:
                    raise
                # 검증할 수 없는 질문이나 후속 턴 재질문 대신 한 번만 요약을 재시도한다.
                can_ask = False
                model_messages.append(HumanMessage('추가 질문은 불가능하다. 제공된 자료의 핵심 내용을 짧게 묶어 답하고 필요한 값은 근거와 함께 제시하라. 계산하지 않는다.'))
        raise AssertionError('unreachable')

    def filter_evidence(assessment: EvidenceAssessment) -> EvidenceAssessment:
        facts = [item for item in assessment.facts if _supported(item, request.chunks, years)]
        conflicts = [conflict for conflict in assessment.conflicts
                     if not _AMBIGUOUS_AMOUNT.search(conflict.description)
                     and all(_supported(value, request.chunks, years) for value in conflict.values)
                     and _numbers(conflict.description) <= _numbers(' '.join(v.content for v in conflict.values))]
        removed = len(facts) != len(assessment.facts) or len(conflicts) != len(assessment.conflicts)
        not_found = list(assessment.not_found)
        if removed and not not_found:
            not_found.append('자료의 일부 내용을 확인하지 못했어요.')
        return assessment.model_copy(update={'facts': facts, 'conflicts': conflicts, 'not_found': not_found})

    result = await assess_chunks(search, request.chunks, invoke=invoke, filter_assessment=filter_evidence)
    if clarification is not None:
        return ToriRecordAnswerResult(status='clarification', clarification_question=clarification[0],
                                      clarification_options=clarification[1])
    status = ('partial' if (result.facts or result.conflicts) and result.not_found
              else 'answered' if (result.facts or result.conflicts) else 'no_evidence')
    return ToriRecordAnswerResult(status=status, facts=result.facts, conflicts=result.conflicts,
                                  not_found=result.not_found)
