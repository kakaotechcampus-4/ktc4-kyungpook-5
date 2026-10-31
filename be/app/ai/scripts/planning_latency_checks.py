"""측정이 끝난 뒤 기대 동작을 검사한다. 검사 시간은 요청 지연에 포함하지 않는다."""

from app.ai import PlanningChatRequest, PlanningPublicResult, parse_resume_state
from app.ai.features.planning.generation.catalog import BY_CODE, PHASE_ORDER


def inspect_result(case, request, result: PlanningPublicResult) -> dict:
    original = request.resume_state
    state, view = result.next_state, result.view
    previous = original.payload.history
    added = state.payload.history[len(previous):]
    tools = [call.name for message in added for call in message.tool_calls]
    generation = view.generation_result
    checks = dict(
        request_matches=result.request_id == request.request_id and result.base_revision == request.base_revision,
        scope_matches=(state.club_id, state.event_id, state.conversation_id) == (
            request.club_id, request.event_id, request.conversation_id),
        json_roundtrip=parse_resume_state(state.model_dump_json()) == state,
        history_prefix_preserved=state.payload.history[:len(previous)] == previous,
        no_search=view.record_lookup is None,
        deferred_topics_preserved=view.draft.deferred_topics == request.draft.deferred_topics,
    )
    expected = request.draft.conditions.model_dump()
    if case.id == 'C2':
        expected['headcount'] = case.expected_headcount
    checks['conditions_match'] = view.draft.conditions.model_dump() == expected
    if case.id != 'C2':
        checks['metadata_preserved'] = view.draft.condition_meta == request.draft.condition_meta
    else:
        checks['other_metadata_preserved'] = {
            key: value for key, value in view.draft.condition_meta.items() if key != 'headcount'
        } == {key: value for key, value in request.draft.condition_meta.items() if key != 'headcount'}
        checks['headcount_metadata'] = (
            view.draft.condition_meta.get('headcount') is not None
            and view.draft.condition_meta['headcount'].status == 'specified'
        )
    checks['changed_fields_match'] = view.changed_fields == (('headcount',) if case.id == 'C2' else ())
    checks['reply_matches_route'] = bool(view.reply) if isinstance(request, PlanningChatRequest) else view.reply is None
    if isinstance(request, PlanningChatRequest):
        checks['new_message_preserved'] = (
            len(added) >= 2 and added[0].role == 'user' and added[0].id == request.message.id
            and added[0].content == request.message.content and added[-1].role == 'assistant'
        )

    if case.id in {'C1', 'C2'}:
        checks['no_generation'] = generation is None and state.payload.generation.preview is None
        checks['expected_tools'] = not tools if case.id == 'C1' else 'update_event_conditions' in tools
        if case.id == 'C1':
            checks['offer_preserved'] = state.payload.generation == original.payload.generation
    else:
        checks['generated'] = generation is not None and generation.status == 'generated'
        checks['expected_tools'] = 'generate_event_plan' in tools if case.id == 'G1' else not tools
        if case.id == 'G2':
            checks['button_history_preserved'] = state.payload.history == previous
        if generation and generation.preview:
            preview = generation.preview
            included = [step.code for step in preview.steps]
            excluded = [step.code for step in preview.excluded_steps]
            checks['catalog_complete'] = (
                len(set(included)) == len(included) and len(set(excluded)) == len(excluded)
                and not set(included) & set(excluded) and set(included) | set(excluded) == set(BY_CODE)
            )
            checks['unknown_dates_preserved'] = all(
                step.starts_at is None and step.deadline is None
                and all(action.due_date is None for action in step.actions) for step in preview.steps
            )
            phases = [PHASE_ORDER.index(step.phase) for step in preview.steps]
            checks['catalog_metadata_matches'] = all(
                step.code in BY_CODE and step.name == BY_CODE[step.code].name
                and step.phase == BY_CODE[step.code].phase and step.actor == BY_CODE[step.code].actor
                and all(action.type in BY_CODE[step.code].actions for action in step.actions)
                for step in preview.steps
            ) and phases == sorted(phases)
            source = 'chat' if case.id == 'G1' else 'button'
            trigger_id = request.message.id if case.id == 'G1' else request.request_id
            checks['preview_matches_request'] = (
                preview.basis_draft == request.draft and preview.trigger.source == source
                and preview.trigger.request_id == trigger_id and generation.model_calls > 0
                and state.payload.generation.preview == preview and view.preview_is_current
            )
        elif generation:
            checks['failed_preview_preserved'] = (
                state.payload.generation.preview == original.payload.generation.preview
            )

    preview = generation.preview if generation else None
    return dict(checks=checks, tool_calls=tools, output=dict(
        generation_status=generation.status if generation else None,
        preview_bytes=len(preview.model_dump_json().encode()) if preview else 0,
        step_count=len(preview.steps) if preview else 0,
        action_count=sum(len(step.actions) for step in preview.steps) if preview else 0,
    ))
