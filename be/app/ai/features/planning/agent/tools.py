"""조건 변경 Tool의 타입과 처리기. LLM 바인딩과 Node 호출은 다음 단계에서 한다."""

from typing import Literal

from pydantic import ValidationError

from ....contracts import ContractModel, NonBlankStr
from ..schemas import ConditionField, ConditionValue, MessageEvidence, PlanningConditions, PlanningMessage
from .state import ConditionMeta, ConditionStatus, PlanningDraft, PlanningTopic, topic_for


class SetCondition(ContractModel):
    op: Literal["SET"]
    change: ConditionValue
    status: ConditionStatus
    evidence: MessageEvidence


class ClearCondition(ContractModel):
    op: Literal["CLEAR"]
    field: ConditionField
    evidence: MessageEvidence


class TopicUpdate(ContractModel):
    topic: PlanningTopic
    evidence: MessageEvidence


class UpdateEventConditionsInput(ContractModel):
    """다음 단계 LLM이 생성할 인자. 값/필드 조합은 공통 ConditionValue로 검증한다."""

    changes: tuple[SetCondition | ClearCondition, ...] = ()
    defer_topics: tuple[TopicUpdate, ...] = ()
    resume_topics: tuple[TopicUpdate, ...] = ()


class ConditionUpdateResult(ContractModel):
    status: Literal["applied", "unchanged", "rejected"]
    draft: PlanningDraft
    changed_fields: tuple[ConditionField, ...] = ()
    reason: NonBlankStr | None = None


def update_event_conditions(
    draft: PlanningDraft,
    request: UpdateEventConditionsInput,
    *,
    current_message: PlanningMessage,
) -> ConditionUpdateResult:
    """변경 묶음을 검증하고 새 초안을 반환한다. 입력 객체·DB는 바꾸지 않는다.

    자연어가 상담인지 설정인지는 LLM이 판단한다. 이 함수는 요청의 근거와
    값의 조합을 검사하며, 근거 문구가 있다고 의미까지 옳다고 보장하지 않는다.
    """
    def reject(reason: str) -> ConditionUpdateResult:
        return ConditionUpdateResult(status="rejected", draft=draft, reason=reason)

    # 1) “그걸로 하자”도 이번 사용자 발화여야 한다. 수락 대상의 해석은 agent 책임이다.
    evidence = [item.evidence for item in (*request.changes, *request.defer_topics, *request.resume_topics)]
    if current_message.role != "user" or any(
        item.message_id != current_message.id or item.quote not in current_message.text
        for item in evidence
    ):
        return reject("변경과 보류에는 이번 사용자 발화에 포함된 근거가 필요해요.")

    fields = [item.change.field if isinstance(item, SetCondition) else item.field for item in request.changes]
    deferred = [item.topic for item in request.defer_topics]
    resumed = [item.topic for item in request.resume_topics]
    set_topics = {topic_for(item.change.field) for item in request.changes if isinstance(item, SetCondition)}
    if len(fields) != len(set(fields)):
        return reject("같은 조건의 변경이 중복됐어요. 하나의 변경으로 정리해 주세요.")
    if len(deferred) != len(set(deferred)) or len(resumed) != len(set(resumed)):
        return reject("같은 주제의 보류 또는 재개가 중복됐어요.")
    if set(deferred) & (set(resumed) | set_topics):
        return reject("같은 주제를 설정·재개하면서 동시에 보류할 수는 없어요.")

    # 2) 원본이 아닌 복사본에 전체 변경을 모은다. 두 날짜를 함께 옮길 때 중간 상태는 검사하지 않는다.
    values = draft.conditions.model_dump()
    meta = dict(draft.condition_meta)
    for item in request.changes:
        if isinstance(item, SetCondition):
            field = item.change.field
            values[field] = item.change.value
            meta[field] = ConditionMeta(status=item.status, evidence=item.evidence)
        else:
            values[item.field] = None
            meta.pop(item.field, None)
    try:
        conditions = PlanningConditions.model_validate(values)
    except ValidationError:
        # 필드별 타입은 입력에서 확인했다. 이 단계의 실패는 최종 날짜 조합의 충돌이다.
        return reject("종료일이 시작일보다 빨라요. 날짜를 다시 정해 주세요.")

    # 3) SET한 주제는 보류를 풀고, 명시한 보류/재개를 적용한다. CLEAR만으로는 보류를 풀지 않는다.
    topics = (set(draft.deferred_topics) - set_topics - set(resumed)) | set(deferred)
    updated = PlanningDraft(conditions=conditions, condition_meta=meta, deferred_topics=tuple(sorted(topics)))
    changed = tuple(field for field in fields if (
        getattr(draft.conditions, field) != getattr(updated.conditions, field)
        or draft.condition_meta.get(field) != updated.condition_meta.get(field)
    ))
    # 4) 값만 같아도 잠정→명시·근거 갱신이면 변화다. 같은 요청의 재적용은 unchanged다.
    unchanged = (conditions == draft.conditions and meta == draft.condition_meta
                 and topics == set(draft.deferred_topics))
    return ConditionUpdateResult(
        status="unchanged" if unchanged else "applied",
        draft=draft if unchanged else updated, changed_fields=changed,
    )
