import pytest
from pydantic import ValidationError
from app.schemas.tori import ToriMessageIn, ToriMessageOut


def test_context_and_clarification_camel_case():
    request = ToriMessageIn.model_validate({'message': '2025 환영회',
        'clarificationContext': {'originalQuestion': '행사 예산'}})
    assert request.clarification_context.original_question == '행사 예산'
    result = ToriMessageOut(intent='record_search', reply='어느 행사?',
        clarification={'originalQuestion':'행사 예산', 'question': '어느 행사?', 'options': ['2025 환영회']})
    assert result.model_dump(by_alias=True)['clarification'] == {
        'originalQuestion':'행사 예산', 'question': '어느 행사?', 'options': ['2025 환영회']}
    assert ToriMessageIn(message='기존 질문').clarification_context is None


@pytest.mark.parametrize('question', ['', '   ', 'x' * 4001])
def test_original_question_is_bounded_nonblank(question):
    with pytest.raises(ValidationError):
        ToriMessageIn(message='답', clarification_context={'originalQuestion': question})


def test_clarification_options_are_bounded_and_empty_is_allowed():
    assert ToriMessageOut(intent='record_search', reply='질문',
        clarification={'originalQuestion':'원질문', 'question': '질문', 'options': []}).clarification.options == []
    with pytest.raises(ValidationError):
        ToriMessageOut(intent='record_search', reply='질문',
            clarification={'originalQuestion':'원질문', 'question': '질문', 'options': ['1','2','3','4']})


def test_context_question_options_are_optional_and_bounded():
    request = ToriMessageIn.model_validate({'message': '첫 번째', 'clarificationContext': {
        'originalQuestion': '행사 예산', 'question': '어느 연도?', 'options': ['2024', '2025']}})
    assert request.clarification_context.options == ['2024', '2025']
    with pytest.raises(ValidationError):
        ToriMessageIn.model_validate({'message': '답', 'clarificationContext': {
            'originalQuestion': '질문', 'question': '  ', 'options': ['2024']}})
    with pytest.raises(ValidationError):
        ToriMessageIn.model_validate({'message': '답', 'clarificationContext': {
            'originalQuestion': '질문', 'options': [' ']}})
