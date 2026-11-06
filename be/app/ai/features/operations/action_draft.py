"""운영 중 공지·발송 Action 하나의 본문 초안을 쓰고, 입력에 없는 값을 지어냈는지 코드로 검사한다.

입력 예: 봄 MT(5/10~5/11, 참가비 45,000원) 모집 공지
  → 모델이 본문만 씀 → find_draft_violations()가 본문의 날짜·요일·금액·시각을 입력과 대조
  → 통과하면 결과, 걸리면 어긴 값을 알려 주고 한 번만 다시 쓰게 함
저장·상태 변경·호출 시점은 BE(#334)가 맡는다.
"""
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from ...contracts import ContractModel
from ...errors import AIInvalidResponseError
from ...llm import ainvoke_structured
from .schemas import ActionDraftRequest, ActionDraftResult, DraftText, _PLACEHOLDER


_PROMPT = (Path(__file__).parent / 'prompts' / 'action_draft.md').read_text(encoding='utf-8')
# 프롬프트를 바꾸면 올린다. 평가 기록(docs/operations-evaluation.md)에 이 값을 함께 남긴다.
PROMPT_VERSION = 'action-draft-v1'
# 첫 호출 1번 + 검사에 걸렸을 때 다시 쓰기 1번.
MAX_ATTEMPTS = 2

_WEEKDAYS = '월화수목금토일'

# ── 날짜 ─────────────────────────────────────────────────────────────────
# 본문에서 날짜로 읽는 표기. 뒤에 "(토)"처럼 괄호 요일이 붙으면 함께 읽는다.
#   "2026년 5월 10일"     → 연도까지 같아야 통과
#   "5월 10일(일)"        → 5/10, 요일 일
#   "5/1까지"             → 5/1  ("1/N 정산"처럼 숫자가 아닌 쪽은 날짜가 아님)
#   "5.10(일)"            → 5/10  (점 표기는 "2.5km"와 헷갈리므로 괄호 요일이 붙을 때만 날짜로 읽음)
#   "~11일"              → 바로 앞 날짜의 월을 이어받아 5/11  (아래 _date_violations 참고)
#   "1박 2일", "3일간", "D-7" → 날짜 아님 (앞에 "N월"도 "~"도 없음)
_DATE = re.compile(
    r'(?:(?P<year>\d{4})\s*년\s*)?(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일'
    r'|(?<![\d/.])(?P<slash_month>\d{1,2})/(?P<slash_day>\d{1,2})(?![\d/])'
    r'|(?<![\d.])(?P<dot_month>\d{1,2})\.(?P<dot_day>\d{1,2})(?=\s*\([월화수목금토일])'
    r'|~\s*(?P<next_day>\d{1,2})\s*일'
)
# 날짜 바로 뒤의 괄호 요일. "(토)", "(토요일)" 모두 읽는다.
_WEEKDAY_AFTER = re.compile(r'\s*\(\s*(?P<weekday>[월화수목금토일])(?:요일)?\s*\)')

# ── 금액 ─────────────────────────────────────────────────────────────────
#   "45,000원", "45000원", "45,000 원" → 45000 으로 읽어 입력과 대조
#   "40명", "1~2개"                    → 원이 아니므로 금액 아님
_AMOUNT = re.compile(r'(?<![\d,])(?P<number>\d{1,3}(?:,\d{3})+|\d+)\s*원')
#   "4만 5천원", "4만원", "4.5만원", "5천 원" → 한글 단위 금액. 읽지 않고 거절한다(프롬프트가 숫자 표기를 요구).
_KOREAN_AMOUNT = re.compile(r'(?:\d[\d,.]*\s*[만천백]\s*)+(?:\d[\d,]*\s*)?원')

# ── 시각 ─────────────────────────────────────────────────────────────────
# 입력에는 시각이 없다. 본문에 시각이 있으면 모두 지어낸 값이다.
#   "오전 9시", "10시까지" → 시각
#   "2시간 걸려요"         → 걸리는 시간이라 시각이 아님 (검사하지 않음)
#   "D-3 시작"             → 숫자와 "시" 사이가 떨어져 있으면 시각으로 읽지 않음
#   "14:00", "9:30"        → 시각
_HOUR = re.compile(r'(?<!\d)\d{1,2}시(?!간|작)')
_CLOCK = re.compile(r'(?<!\d)\d{1,2}:\d{2}(?!\d)')


def _allowed_dates(request: ActionDraftRequest) -> set[date]:
    """본문에 써도 되는 날짜: 행사 시작·종료일, 단계 시작·마감일, Action 기한, 오늘."""
    candidates = (request.event.start_date, request.event.end_date, request.step.starts_on,
                  request.step.deadline, request.action.due_date, request.today)
    return {value for value in candidates if value is not None}


def _allowed_amounts(request: ActionDraftRequest) -> set[int]:
    """본문에 써도 되는 금액: 1인 참가비와 Action 금액. 총예산·계산값은 허용하지 않는다."""
    return {value for value in (request.event.fee_per_person, request.action.amount) if value is not None}


def _label(month: int, day: int) -> str:
    return f'{month}월 {day}일'


def _date_violations(text: str, allowed: set[date]) -> list[str]:
    """본문의 날짜가 허용 날짜에 있는지, 붙은 요일이 그 날짜의 요일과 같은지 본다."""
    violations = []
    # "~11일"이 이어받을 앞 날짜의 월과 그 날짜가 끝난 위치. 바로 앞이 날짜일 때만 이어받는다.
    # 예: "5월 10일(일)~11일" → 5/11. "행사 1~2일 전" → 앞이 날짜가 아니므로 날짜로 읽지 않음.
    last_month, last_end = None, -1
    for match in _DATE.finditer(text):
        year = None
        if match['month']:
            year, month, day = match['year'], int(match['month']), int(match['day'])
        elif match['slash_month']:
            month, day = int(match['slash_month']), int(match['slash_day'])
            if not (1 <= month <= 12 and 1 <= day <= 31):
                continue  # "24/7"처럼 날짜일 수 없는 값은 날짜로 보지 않는다.
        elif match['dot_month']:
            month, day = int(match['dot_month']), int(match['dot_day'])
        else:
            if last_month is None or text[last_end:match.start()].strip():
                continue
            month, day = last_month, int(match['next_day'])

        end = match.end()
        weekday_match = _WEEKDAY_AFTER.match(text, end)
        if weekday_match:
            end = weekday_match.end()
        last_month, last_end = month, end

        # "~11일"처럼 월이 빠진 표기는 이어받은 날짜도 함께 보여 준다.
        shown = match.group(0).strip()
        if shown != _label(month, day) and not match['year']:
            shown = f'{shown}({_label(month, day)})'
        same_day = [d for d in allowed
                    if d.month == month and d.day == day and (year is None or d.year == int(year))]
        if not same_day:
            violations.append(f'본문의 날짜가 입력에 없습니다: {shown}')
            continue
        if weekday_match:
            written = weekday_match['weekday']
            actual = {_WEEKDAYS[d.weekday()] for d in same_day}
            if written not in actual:
                correct = '·'.join(sorted(actual))
                violations.append(f'본문의 요일이 날짜와 맞지 않습니다: {_label(month, day)}({written}) '
                                  f'→ {_label(month, day)}은 {correct}요일')
    return violations


def _amount_violations(text: str, allowed: set[int]) -> tuple[list[str], str]:
    """한글 단위 금액은 거절하고, 숫자 금액은 허용 금액과 대조한다. 남은 본문도 돌려준다."""
    violations = []
    for match in _KOREAN_AMOUNT.finditer(text):
        violations.append(f'본문의 금액을 숫자로 쓰지 않았습니다: {match.group(0).strip()} '
                          '(45,000원처럼 숫자로 씁니다)')
    # "4만 5000원"의 "5000원"을 다시 읽지 않도록 한글 금액 자리를 지운다.
    rest = _KOREAN_AMOUNT.sub(' ', text)
    for match in _AMOUNT.finditer(rest):
        if int(match['number'].replace(',', '')) not in allowed:
            violations.append(f'본문의 금액이 입력에 없습니다: {match.group(0).strip()}')
    return violations, rest


def _time_violations(text: str) -> list[str]:
    found = [m.group(0).strip() for m in _HOUR.finditer(text)]
    found += [m.group(0) for m in _CLOCK.finditer(text)]
    return [f'본문의 시각이 입력에 없습니다: {value} (시각은 [집결 시간]처럼 비워 둡니다)' for value in found]


def find_draft_violations(content: str, request: ActionDraftRequest) -> tuple[str, ...]:
    """본문에서 입력에 없는 날짜·요일·금액·시각을 찾아, 모델에게 다시 알려 줄 문장으로 돌려준다.

    빈 튜플이면 통과다. 예(입력: 행사 5/10~5/11, 기한 5/1, 참가비 45,000원, 오늘 4/20):
      "5월 10일(일)~11일(월)"   → ()
      "5월 10일~5월 12일"       → ("본문의 날짜가 입력에 없습니다: 5월 12일",)
      "참가비 4만 5천원"        → ("본문의 금액을 숫자로 쓰지 않았습니다: 4만 5천원 ...",)
      "오전 9시 정문 집결"      → ("본문의 시각이 입력에 없습니다: 9시 ...",)
    세부 장소·인원처럼 코드로 잡기 어려운 값은 보지 않는다(프롬프트 규칙과 평가의 수동 확인).
    """
    # [집결 시간], [010-0000-0000] 같은 자리표시 안은 지어낸 값이 아니므로 검사에서 뺀다.
    text = _PLACEHOLDER.sub(' ', content)
    violations, text = _amount_violations(text, _allowed_amounts(request))
    violations += _date_violations(text, _allowed_dates(request))
    violations += _time_violations(text)
    return tuple(dict.fromkeys(violations))


# ── 본문 작성 ────────────────────────────────────────────────────────────


class _DraftOutput(ContractModel):
    """모델이 돌려주는 값. 본문만 쓰게 하고 unknowns는 코드가 본문에서 뽑는다."""

    content: DraftText


@dataclass(frozen=True)
class DraftAttempt:
    """모델 호출 한 번의 본문과 코드 검사 결과. 평가 스크립트가 호출 횟수와 함께 읽는다."""

    content: str
    violations: tuple[str, ...]


def _input_message(request: ActionDraftRequest) -> HumanMessage:
    """요청 JSON에 날짜별 요일만 더해 데이터로 넘긴다.

    요일은 모델이 계산하면 틀리기 쉬워 코드가 계산해 준다. 예: "2026-05-10" → "일".
    """
    data = request.model_dump(mode='json')
    data['weekdays'] = {d.isoformat(): _WEEKDAYS[d.weekday()] for d in sorted(_allowed_dates(request))}
    return HumanMessage(json.dumps(data, ensure_ascii=False))


def _retry_message(violations: tuple[str, ...]) -> HumanMessage:
    """어긴 값을 그대로 알려 주고 본문 전체를 다시 쓰게 한다."""
    lines = '\n'.join(f'- {violation}' for violation in violations)
    return HumanMessage(
        '앞에서 쓴 본문에 입력과 맞지 않는 값이 있습니다.\n'
        f'{lines}\n'
        '이 값을 입력에 있는 값으로 고치거나 대괄호로 비워 본문 전체를 다시 쓰세요.'
    )


async def _write(messages: list) -> str:
    output = await ainvoke_structured(messages, _DraftOutput)
    try:
        return _DraftOutput.model_validate(output).content
    except ValidationError as error:
        raise AIInvalidResponseError('본문 초안 응답 형식이 올바르지 않습니다') from error


async def draft_attempts(request: ActionDraftRequest) -> tuple[DraftAttempt, ...]:
    """본문을 쓰고 검사한다. 검사에 걸리면 어긴 값을 알려 주고 한 번만 다시 쓴다.

    호출한 순서대로 시도를 모두 돌려준다(1개 또는 2개). 마지막 시도에 어긴 값이 남았는지는
    부르는 쪽이 판단한다. 공개 함수는 draft_action_content이고, 이 함수는 평가 스크립트도 쓴다.
    """
    # 요청 JSON은 데이터이므로 지시문과 섞지 않고 별도 사용자 메시지로만 보낸다.
    messages = [SystemMessage(_PROMPT), _input_message(request)]
    attempts: list[DraftAttempt] = []
    for _ in range(MAX_ATTEMPTS):
        content = await _write(messages)
        attempt = DraftAttempt(content=content, violations=find_draft_violations(content, request))
        attempts.append(attempt)
        if not attempt.violations:
            break
        # 다시 쓸 때는 앞 본문과 어긴 값을 함께 보여 준다.
        messages = [*messages, AIMessage(json.dumps({'content': content}, ensure_ascii=False)),
                    _retry_message(attempt.violations)]
    return tuple(attempts)


async def draft_action_content(request: ActionDraftRequest) -> ActionDraftResult:
    """공지·발송 Action 하나의 본문 초안. 다시 써도 검사에 걸리면 AIInvalidResponseError를 낸다."""
    last = (await draft_attempts(request))[-1]
    if last.violations:
        raise AIInvalidResponseError('다시 쓴 본문에도 입력에 없는 값이 있습니다')
    return ActionDraftResult(content=last.content)
