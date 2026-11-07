"""운영 Action 본문 초안의 코드 검사(#333 판정 표)를 고정한다.

입력은 이슈의 예와 같다: 행사 2026-05-10~05-11, 단계 기한 05-01, 참가비 45,000원, 오늘 04-20.
2026-05-10은 일요일, 05-11은 월요일이다. 이슈 표의 "(토)·(일)"은 요일을 잘못 적은 예라
여기서는 실제 요일로 고쳐 같은 규칙(요일은 날짜에서 계산한 값과 같아야 함)을 확인한다.
"""
from datetime import date

import pytest

import app.ai as ai
from app.ai.features.operations.action_draft import find_draft_violations


def spring_mt(**action_updates):
    action = dict(type='NOTICE', title='모집 공지 올리기', due_date=date(2026, 5, 1))
    action.update(action_updates)
    return ai.ActionDraftRequest(
        club_name='경북대 등산 동아리',
        event=ai.ActionDraftEvent(title='봄 MT', event_type='MT', start_date=date(2026, 5, 10),
                                  end_date=date(2026, 5, 11), location='가평', expected_headcount=40,
                                  fee_per_person=45000),
        step=ai.ActionDraftStep(code='RECRUIT_NOTICE', name='모집 공지', deadline=date(2026, 5, 1)),
        action=ai.ActionDraftAction(**action),
        today=date(2026, 4, 20),
    )


def check(content, request=None):
    return find_draft_violations(content, request or spring_mt())


# ── 판정 표: 통과 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('content', [
    '5월 10일(일)~11일(월)',       # ~11일은 앞의 월을 이어받아 5/11
    '5월 10일(일) ~ 11일(월요일)',
    '5/1까지 신청해 주세요',         # M/D 표기도 날짜로 읽음
    '참가비: 45,000원',
    '참가비: 45000원',              # 쉼표 유무는 같은 값
    '집결: [집결 시간] / 입금: [계좌]',  # 자리표시
])
def test_판정표에서_통과하는_본문(content):
    assert check(content) == ()


# ── 판정 표: 거절 ───────────────────────────────────────────────────────────

def test_입력에_없는_날짜는_거절한다():
    assert check('5월 10일~5월 12일') == ('본문의 날짜가 입력에 없습니다: 5월 12일',)


def test_요일이_날짜와_다르면_거절한다():
    # 5/10은 일요일이다.
    assert check('5월 10일(토)') == ('본문의 요일이 날짜와 맞지 않습니다: 5월 10일(토) → 5월 10일은 일요일',)


def test_한글_금액은_읽지_않고_거절한다():
    (violation,) = check('참가비 4만 5천원')
    assert violation.startswith('본문의 금액을 숫자로 쓰지 않았습니다: 4만 5천원')


def test_입력에_없는_계산값은_거절한다():
    # 40명 × 45,000원처럼 계산한 값은 입력에 없다.
    assert check('총 1,800,000원이 모입니다') == ('본문의 금액이 입력에 없습니다: 1,800,000원',)


@pytest.mark.parametrize('content, value', [('오전 9시 정문 집결', '9시'), ('14:00 출발', '14:00')])
def test_입력에_없는_시각은_거절한다(content, value):
    (violation,) = check(content)
    assert violation.startswith(f'본문의 시각이 입력에 없습니다: {value}')


# ── 판정 표 밖에서 헷갈리기 쉬운 표기 ─────────────────────────────────────────

@pytest.mark.parametrize('content', [
    '1인당 간식은 1~2개씩 챙겨 주세요',     # 범위 숫자는 날짜·금액이 아님
    '예상 인원은 40명이에요',               # 인원은 코드가 보지 않음(수동 확인)
    '문의: [010-1234-5678]',               # 자리표시 안의 숫자는 검사하지 않음
    '마감 D-7! 서둘러 주세요',
    '1박 2일 일정으로 다녀옵니다',           # "2일"은 앞에 월이 없어 날짜가 아님
    '행사 1~2일 전에 다시 안내할게요',       # "~2일"이 이어받을 앞 날짜가 없음
    '가평까지 2시간 정도 걸려요',            # 걸리는 시간은 시각이 아님
    '오늘(4월 20일)부터 신청을 받아요',       # 오늘도 허용 날짜
    '비용은 1/N로 나눠요',
])
def test_날짜나_시각이나_금액이_아닌_표기는_통과한다(content):
    assert check(content) == ()


def test_연도를_쓰면_연도까지_같아야_한다():
    assert check('2026년 5월 10일') == ()
    assert check('2025년 5월 10일') == ('본문의 날짜가 입력에 없습니다: 2025년 5월 10일',)


def test_이어받은_날짜도_입력에_있어야_한다():
    assert check('5월 10일~12일') == ('본문의 날짜가 입력에 없습니다: ~12일(5월 12일)',)


def test_점_표기는_괄호_요일이_붙을_때만_날짜로_읽는다():
    assert check('5.10(일)~5.11(월)') == ()
    assert check('5.12(화)') == ('본문의 날짜가 입력에 없습니다: 5.12(5월 12일)',)
    assert check('거리는 2.5km예요') == ()


def test_M_D_표기도_요일을_대조한다():
    assert check('5/1(목)까지') == ('본문의 요일이 날짜와 맞지 않습니다: 5월 1일(목) → 5월 1일은 금요일',)


@pytest.mark.parametrize('content', ['참가비 4만원', '4.5만원', '5천 원', '4만 5000원'])
def test_한글_단위가_섞인_금액은_모두_거절한다(content):
    (violation,) = check(content)
    assert violation.startswith('본문의 금액을 숫자로 쓰지 않았습니다')


def test_Action_금액도_허용한다():
    assert check('예약금 100,000원', spring_mt(amount=100000)) == ()
    assert check('예약금 100,000원') == ('본문의 금액이 입력에 없습니다: 100,000원',)


def test_비어_있는_입력_날짜는_허용하지_않는다():
    # Action 기한이 없으면 5/1은 단계 기한으로만 허용된다. 둘 다 없으면 거절.
    request = spring_mt(due_date=None)
    assert check('5월 1일 마감', request) == ()
    no_deadline = request.model_copy(update={'step': request.step.model_copy(update={'deadline': None})})
    assert check('5월 1일 마감', no_deadline) == ('본문의 날짜가 입력에 없습니다: 5월 1일',)


def test_어긴_값을_모두_모으고_같은_문장은_한_번만_낸다():
    violations = check('5월 12일, 5월 12일 오전 9시 집결, 참가비 50,000원')
    assert violations == (
        '본문의 금액이 입력에 없습니다: 50,000원',
        '본문의 날짜가 입력에 없습니다: 5월 12일',
        '본문의 시각이 입력에 없습니다: 9시 (시각은 [집결 시간]처럼 비워 둡니다)',
    )


def test_이슈_예시_본문은_실제_요일로_쓰면_통과한다():
    content = ('📢 봄 MT 참가자 모집\n5월 10일(일)~11일(월) 가평으로 MT를 갑니다!\n'
               '참가비: 45,000원 / 신청 마감: 5월 1일\n신청 방법: [신청 링크]')
    assert check(content) == ()
