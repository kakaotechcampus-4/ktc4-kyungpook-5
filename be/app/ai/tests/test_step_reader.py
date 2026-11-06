"""생성 모델 JSON 조각에서 단계 코드를 찾는 읽기 코드(#389).

조각이 어디서 끊기든, 문자열 안에 무엇이 있든, steps 배열의 code만 순서대로 한 번씩 찾아야 한다.
"""
import json

import pytest

from app.ai.features.planning.generation.step_reader import StepCodeReader
from app.ai.planning_catalog import PLANNING_STEP_NAMES

ALL_CODES = [str(code) for code in PLANNING_STEP_NAMES]


def read_all(chunks):
    reader = StepCodeReader()
    return [found for chunk in chunks for found in reader.feed(chunk)]


def split_every(text, size):
    return [text[i:i + size] for i in range(0, len(text), size)]


def composition_text(codes, *, indent=None):
    # 실제 PlanComposition 모양. purpose·행동 제목에 속이기 쉬운 글자를 넣는다.
    steps = [{"code": code,
              "purpose": f'"code":"BOOK_VENUE" 같은 글자나 {{ [ ]] }} 괄호, 역슬래시 \\ 와 줄바꿈\n도 들어갈 수 있어요 ({i})',
              "starts_at": None, "deadline": None,
              "actions": [{"type": "notice", "title": '{"code":"REFUND_FEES"}', "due_date": None,
                           "meta": {"code": "COLLECT_FEES"}}]}
             for i, code in enumerate(codes)]
    return json.dumps({"steps": steps,
                       "excluded_steps": [{"code": "DEMAND_SURVEY", "reason": "이미 참여 의사를 확인했어요"}],
                       "assumptions": [{"content": '"steps":[{"code":"EVENT_DAY"}]', "fact_ids": []}],
                       "open_questions": ["행사 날짜"], "warnings": []}, ensure_ascii=False, indent=indent)


def test_이슈의_예시_조각():
    reader = StepCodeReader()
    assert reader.feed('{"steps":[{"co') == []
    assert reader.feed('de":"ASSIGN_ROL') == []
    assert reader.feed('ES","purpose":"역할을 \\"code\\" 기준으로 나눠요 {임시}"') == [(0, "ASSIGN_ROLES")]
    assert reader.feed(',"actions":[]},{"code":"RESEARCH_VENUE",') == [(1, "RESEARCH_VENUE")]


@pytest.mark.parametrize("size", [1, 2, 3, 7, 16, 61, 10_000])
def test_조각_크기와_상관없이_13단계를_순서대로_한_번씩_찾는다(size):
    text = composition_text(ALL_CODES)
    assert read_all(split_every(text, size)) == list(enumerate(ALL_CODES))


def test_줄바꿈과_공백이_있는_JSON도_읽는다():
    text = composition_text(ALL_CODES[:3], indent=2)
    assert read_all(split_every(text, 5)) == list(enumerate(ALL_CODES[:3]))


def test_제외_단계와_행동_안의_code와_문자열_속_code는_무시한다():
    found = read_all([composition_text(["EVENT_DAY"])])
    # excluded_steps의 DEMAND_SURVEY, 행동 meta의 COLLECT_FEES, 글 속 BOOK_VENUE·REFUND_FEES는 나오지 않는다
    assert found == [(0, "EVENT_DAY")]


def test_code가_맨_앞이_아니어도_그_단계의_위치로_찾는다():
    text = '{"steps":[{"purpose":"x","code":"ASSIGN_ROLES"},{"code":"EVENT_DAY"}]}'
    assert read_all(split_every(text, 4)) == [(0, "ASSIGN_ROLES"), (1, "EVENT_DAY")]


def test_steps가_맨_앞이_아니어도_steps의_code만_찾는다():
    text = '{"excluded_steps":[{"code":"DEMAND_SURVEY","reason":"x"}],"steps":[{"code":"EVENT_DAY"}]}'
    assert read_all([text]) == [(0, "EVENT_DAY")]


def test_한_단계에_code가_두_번_와도_한_번만_알린다():
    text = '{"steps":[{"code":"ASSIGN_ROLES","code":"EVENT_DAY"},{"code":"BOOK_VENUE"}]}'
    assert read_all([text]) == [(0, "ASSIGN_ROLES"), (1, "BOOK_VENUE")]


@pytest.mark.parametrize("text", ['', '}}]]', '"""', '{"steps":"ASSIGN_ROLES"}', '{"steps":[{"code":12}]}',
                                  '{"steps":[{"code":"ASSIGN_ROLES', '[{"code":"EVENT_DAY"}]'])
def test_깨진_글도_예외_없이_지나간다(text):
    # 진행 표시용이라 멈추지 않는다. 최종 판단은 다 받은 뒤의 형식 검사가 한다.
    assert read_all(split_every(text, 3) or ['']) == []
