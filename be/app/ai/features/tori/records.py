"""토리 질문의 근거를 검색된 청크에서만 정리한다."""
import json
import re
from datetime import date
from decimal import Decimal
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


# 숫자 검사: 답변의 금액·인원·날짜 숫자가 인용한 청크 원문에 있는지 코드로 확인한다.
# 표기만 맞춰 비교하고(쉼표, ₩·\ 표시, 한글 큰 단위), 합산·나눗셈 같은 계산은 하지 않는다.
#   "45,000원" "45000\" "₩45,000"  → ("45000", "원")
#   "4만 5천원" "4.5만원"            → ("45000", "원")
#   "참가 인원: 40"                  → ("40", "")      단위 없음
_SIGN = r'(?:[+\-−]|마이너스|음수|플러스)'
# 원 표시는 숫자 앞(₩45,000)과 뒤(45000\) 모두 쓴다. 한글 윈도우는 \를 ₩로 보여 준다.
_WON_MARK = r'[₩\\]'
# 원만 지원한다. 외화 표시는 값을 읽지 않고, 원 금액과 같은 값으로 통과하지 않게만 표시한다.
_FOREIGN_BEFORE = r'(?:US\$|\$|€|¥|£|USD|JPY|EUR|CNY)'
_FOREIGN_AFTER = r'(?:달러|엔|유로|위안|USD|JPY|EUR|CNY|\$|€|¥|£)'
_BIG = r'(?:조|억|만|천|백|십)'
# 큰 단위가 붙은 부분이 이어지면 한 금액이다. 예: "4만 5천", "1억 2천만", "2 백만"
_AMOUNT = rf'\d[\d,]*(?:\.\d+)?(?![\d.])(?:\s*{_BIG}+(?:\s*\d[\d,]*(?:\.\d+)?\s*{_BIG}+)*)?'
_NUMBER = re.compile(
    rf'(?<![\d.])(?P<before>{_WON_MARK}|{_FOREIGN_BEFORE})?\s*(?P<sign>{_SIGN})?\s*'
    rf'(?P<before2>{_WON_MARK}|{_FOREIGN_BEFORE})?\s*(?P<amount>{_AMOUNT})\s*'
    rf'(?P<unit>원|명|개|건|%|년|월|일|{_WON_MARK}|{_FOREIGN_AFTER})?')
# 한글 수사는 단위가 붙을 때만 숫자로 본다("일", "이"는 일반 글자와 겹친다).
_KOREAN_NUMBER = re.compile(
    rf'(?<![\d.])(?P<sign>{_SIGN})?\s*(?P<word>[영공일이삼사오육칠팔구십백천만억조]+|'
    r'(?:스물|서른|마흔|쉰|예순|일흔|여든|아흔)(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉)?|스무|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)'
    r'\s*(?P<unit>원|명|개|건|%|퍼센트|년|월|일)')
_AMBIGUOUS_AMOUNT = re.compile(r'\(\s*(?:[₩\\]\s*)?(?:\d[\d,]*(?:\.\d+)?|[영공일이삼사오육칠팔구십백천만억조]+)\s*(?:조|억|만|천|백|십)?\s*(?:원|₩|\\)?\s*\)')
_YEAR = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\s*(?:원|₩|\\|명|개|건|%|월|일|만원|억원))(?=년|(?:에서|으로|부터|까지|에는|의|에|은|는|이|가|도|과|와)(?![가-힣])|[_\W]|$)')
_YEAR_RANGE = re.compile(r'(?<!\d)((?:19|20)\d{2})(?:\s*년)?\s*(?:부터|에서|~|〜|～|–|—|-)\s*((?:19|20)\d{2})(?!\d)')
_BIG_VALUE = {'십': 10, '백': 100, '천': 1000, '만': 10**4, '억': 10**8, '조': 10**12}
_KOREAN_DIGIT = {'영': 0, '공': 0, '일': 1, '이': 2, '삼': 3, '사': 4, '오': 5, '육': 6, '칠': 7, '팔': 8, '구': 9}


def _requested_years(text: str) -> set[str]:
    years = set(_YEAR.findall(text))
    for start, end in _YEAR_RANGE.findall(text):
        if int(start) <= int(end):
            years.update(str(year) for year in range(int(start), int(end) + 1))
    return years


def _amount_value(amount: str) -> str:
    """아라비아 숫자 금액을 값으로 읽는다. 큰 단위 순서가 어긋나면 원래 표기를 그대로 둔다.

    "45,000.00" → "45000", "4만5천" → "45000", "10.5만" → "105000", "1억2천만" → "120000000"
    """
    total, last = Decimal(0), None
    for digits, units in re.findall(r'(\d[\d,]*(?:\.\d+)?)([조억만천백십]*)', amount):
        scale = 1
        for unit in units:  # "천만" = 1000 × 10000
            scale *= _BIG_VALUE[unit]
        if last is not None and scale >= last:
            return amount
        last = scale
        # 소수는 Decimal로 계산한다. float이면 4.5 × 10000이 44999.99…가 될 수 있다.
        total += Decimal(digits.replace(',', '')) * scale
    return format(total.normalize(), 'f')


def _korean_value(word: str) -> str:
    """한자어 수사를 값으로 읽는다. 고유어 수사(한·스무)는 원래 표기 그대로 두어 같은 표기만 맞춘다.

    "십만" → "100000", "이십" → "20", "백만" → "1000000", "한" → "한"
    """
    if any(ch not in _KOREAN_DIGIT and ch not in _BIG_VALUE for ch in word):
        return word
    total = section = 0
    digit = None
    for ch in word:
        if ch in _KOREAN_DIGIT:
            if digit is not None:  # "이이"처럼 숫자가 이어지면 수사가 아니다
                return word
            digit = _KOREAN_DIGIT[ch]
        elif ch in '십백천':
            section += (1 if digit is None else digit) * _BIG_VALUE[ch]
            digit = None
        else:
            total += ((section + (digit or 0)) or 1) * _BIG_VALUE[ch]
            section, digit = 0, None
    return str(total + section + (digit or 0))


def _sign(sign: str | None) -> str:
    return '-' if sign in ('-', '−', '마이너스', '음수') else ''


def _unit(*marks: str | None) -> str:
    marks = tuple(mark for mark in marks if mark)
    if any(re.fullmatch(f'{_FOREIGN_BEFORE}|{_FOREIGN_AFTER}', mark) for mark in marks):
        return '외화'
    if any(mark in ('원', '₩', '\\') for mark in marks):
        return '원'
    return next(('%' if mark == '퍼센트' else mark for mark in marks), '')


def _numbers(text: str) -> set[tuple[str, str]]:
    """글 속 숫자를 (값, 단위)로 모은다. 단위는 원·명·개·건·%·년·월·일·외화, 없으면 ""."""
    # 일반 단어 '행사명'은 한글 수사 '사명'과 겹치므로 먼저 제외한다.
    text = _AMBIGUOUS_AMOUNT.sub('', text).replace('행사명', '')
    matches = list(_NUMBER.finditer(text))
    numbers = {(_sign(m['sign']) + _amount_value(re.sub(r'\s', '', m['amount'])),
                _unit(m['before'], m['before2'], m['unit']))
               for m in matches}
    for m in _KOREAN_NUMBER.finditer(text):
        # 아라비아 숫자 금액 안의 큰 단위(예: 10 만원, 1억 2천만원의 "만원")는 별도 한글 수사가 아니다.
        before = text[:m.start()].rstrip()
        if (before and (before[-1].isdigit() or before[-1] == '.')
                or any(n.start() <= m.start() < n.end() for n in matches)):
            continue
        numbers.add((_sign(m['sign']) + _korean_value(m['word']), _unit(m['unit'])))
    return numbers


def _found(claimed: set[tuple[str, str]], evidence: set[tuple[str, str]]) -> bool:
    """답변의 숫자마다 원문에 같은 값이 있는지 본다. 단위는 양쪽에 다 있을 때만 같아야 한다.

    원문 "금액: 45000"과 답변 "45,000원" → 원문에 단위가 없어 값만 비교 → 통과
    원문 "45,000원"과 답변 "45,000명"  → 단위가 달라 실패
    """
    return all(any(value == v and (unit == u or not unit or not u) for v, u in evidence)
               for value, unit in claimed)


def _supported(item: EvidenceItem, chunks: tuple[RetrievedChunk, ...], years: set[str]) -> bool:
    if _AMBIGUOUS_AMOUNT.search(item.content):
        return False
    cited = [chunks[int(key[1:]) - 1] for key in item.chunk_ids]
    evidence = '\n'.join(f'{chunk.text} {chunk.source.file_name} {chunk.source.location.label}' for chunk in cited)
    text_numbers = _numbers('\n'.join(chunk.text for chunk in cited))
    evidence_years = set(_YEAR.findall(evidence))
    # 문서명 연도만 예외로 허용하고 금액·인원은 본문에서 확인한다.
    claimed = {(value, unit) for value, unit in _numbers(item.content)
               if not (unit in ('', '년') and value in evidence_years)}
    claim_years = set(_YEAR.findall(item.content))
    return (bool(cited) and _found(claimed, text_numbers)
            and (not years or (bool(years & evidence_years) and claim_years <= years)))


async def answer_tori_records(request: ToriRecordAnswerRequest) -> ToriRecordAnswerResult:
    if not request.chunks:
        return ToriRecordAnswerResult(status='no_evidence', not_found=(request.question,))
    # 이 호출은 검색을 다시 하지 않는다. BE가 승인한 청크 외의 출처는 생성할 수 없다.
    search = RecordSearchRequest(club_id='provided', query=request.question, today=request.today)
    years = _requested_years(request.follow_up or '') or _requested_years(request.question)
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
                     and _found(_numbers(conflict.description), _numbers(' '.join(v.content for v in conflict.values)))]
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
