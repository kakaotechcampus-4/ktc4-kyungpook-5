# 행사계획 코드 따라가기 — 조건을 담고 검사하기

현재 범위는 작업 1의 내부 조건 타입이다. 작업 2의 LLM 추출과 작업 3의 질문 선택은 후속 PR에서 연결하며 이 문서도 함께 갱신한다.

## 입력 → 코드 → 출력

```python
from app.ai.features.planning.schemas import PlanningConditions

conditions = PlanningConditions.model_validate({
    "headcount": 40, "fee_per_person": 0, "location": None,
})
print(conditions.headcount)       # 40
print(conditions.fee_per_person)  # 0: 무료
print(conditions.location)        # None: 미정
```

[schemas.py](../features/planning/schemas.py)의 `PlanningConditions`는 특정 시점의 조건 묶음인 스냅샷이다. 값을 임의로 추측하지 않으며, 이 객체를 만들었다고 BE에 저장된 것은 아니다.

입력 `headcount=0` → `Field(strict=True, ge=1)` → 검증 오류다. 숫자 문자열·bool·실수도 인원으로 자동 변환하지 않는다. 입력 `fee_per_person=0` → 금액의 `ge=0` → 유효한 무료 행사다. `None`은 무료와 구분되는 미정 값이다.

날짜는 정확한 YYYY-MM-DD 문자열 또는 date 객체를 받는다. `_require_calendar_date`가 datetime·불완전한 날짜·timestamp를 거절하고 `_require_ordered_dates`가 최종 날짜 쌍을 검사한다. 시작일만 있으면 종료일 미정을 허용하며, 종료일이 시작일보다 빠르면 거절한다.

현재 타입은 값의 형식을 검사한다. 대화에서 말한 인원이 올해 확정값인지 작년 참고값인지 판단하는 것은 작업 2의 LLM 추출 책임이다. 기존 공개 `EventConditions`와 내부 타입을 분리했으며 공개 facade·LangGraph 실행 그래프·DB 저장은 아직 연결하지 않았다.

세부 필드와 후속 흐름은 [설계 초안](plan_architecture.md), 검증 예시는 [조건 테스트](../tests/test_planning_conditions.py)를 참고한다.
