"""운영 Action 본문 초안(#333)의 입력·출력 형식을 고정한다.

BE(#334)·FE(#335)가 이 형식으로 가짜 응답을 만들어 먼저 진행하므로, 바뀌면 여기서 먼저 깨지게 한다.
"""
import asyncio
from datetime import date

import pytest
from pydantic import ValidationError

import app.ai as ai


def spring_mt(**event_updates):
    """이슈 #333의 예시: 봄 MT 모집 공지."""
    event = dict(title='봄 MT', event_type='MT', start_date=date(2026, 5, 10), end_date=date(2026, 5, 11),
                 location='가평', expected_headcount=40, fee_per_person=45000)
    event.update(event_updates)
    return ai.ActionDraftRequest(
        club_name='경북대 등산 동아리',
        event=ai.ActionDraftEvent(**event),
        step=ai.ActionDraftStep(code='RECRUIT_NOTICE', name='모집 공지', deadline=date(2026, 5, 1)),
        action=ai.ActionDraftAction(type='NOTICE', title='모집 공지 올리기', due_date=date(2026, 5, 1)),
        today=date(2026, 4, 20),
    )


def test_BE가_테이블_값으로_만든_입력을_받는다():
    request = spring_mt()

    assert request.event.fee_per_person == 45000
    assert request.step.starts_on is None and request.step.deadline == date(2026, 5, 1)
    # 모델에는 JSON으로 넘긴다. 날짜는 시각 없는 날짜 문자열이어야 한다.
    data = request.model_dump(mode='json')
    assert data['step']['deadline'] == '2026-05-01' and data['today'] == '2026-04-20'


def test_장소가_정해지지_않은_행사도_받는다():
    assert spring_mt(location=None, end_date=None).event.location is None


def test_운영_중인_행사에는_시작일이_있어야_한다():
    with pytest.raises(ValidationError):
        spring_mt(start_date=None)


def test_종료일이_시작일보다_빠르면_거절한다():
    with pytest.raises(ValidationError):
        spring_mt(end_date=date(2026, 5, 9))


def test_총예산은_입력에_넣지_않는다():
    # 공지에 쓸 일이 없고, 넣으면 금액 검사가 허용하는 값만 늘어난다.
    with pytest.raises(ValidationError):
        spring_mt(budget_total=1800000)


@pytest.mark.parametrize('action_type', ['CONTRACT', 'TRANSFER', 'EXPENSE', 'CONFIRMATION'])
def test_공지와_발송_말고는_초안_대상이_아니다(action_type):
    with pytest.raises(ValidationError):
        ai.ActionDraftAction(type=action_type, title='예약금 보내기')


def test_발송_Action도_받는다():
    action = ai.ActionDraftAction(type='EXTERNAL_SEND', title='미응답자에게 다시 알리기')
    assert action.type == 'EXTERNAL_SEND'


def test_unknowns는_본문의_자리표시에서_나온_순서대로_뽑는다():
    result = ai.ActionDraftResult(content=(
        '📢 봄 MT 참가자 모집\n'
        '5월 10일(토)~11일(일) 장소: [장소 미정]\n'
        '참가비: 45,000원 / 신청 마감: 5월 1일\n'
        '신청 방법: [신청 링크]\n'
        '문의: [연락처] (장소는 [장소 미정] 확정 후 다시 안내)'
    ))

    assert result.unknowns == ('장소 미정', '신청 링크', '연락처')


def test_자리표시가_없으면_unknowns도_비어_있다():
    assert ai.ActionDraftResult(content='5월 10일 MT 참가 의사를 알려 주세요.').unknowns == ()


def test_unknowns는_결과를_만들_때_넘기는_값이_아니다():
    # 본문과 어긋난 unknowns를 가짜 응답에서도 만들 수 없게 한다.
    with pytest.raises(ValidationError):
        ai.ActionDraftResult(content='신청 방법: [신청 링크]', unknowns=('신청 방법',))


def test_BE에_넘기는_결과에는_unknowns가_함께_담긴다():
    data = ai.ActionDraftResult(content='계좌: [계좌]').model_dump(mode='json')
    assert data == {'content': '계좌: [계좌]', 'unknowns': ['계좌']}


@pytest.mark.parametrize('content', ['', '   ', '가' * 1501])
def test_빈_본문과_너무_긴_본문은_거절한다(content):
    with pytest.raises(ValidationError):
        ai.ActionDraftResult(content=content)


def test_구현_전에는_호출하면_NotImplementedError를_낸다():
    # BE는 이 오류도 실패(FAILED)로 저장한다(#334 오류 처리).
    with pytest.raises(NotImplementedError):
        asyncio.run(ai.draft_action_content(spring_mt()))
