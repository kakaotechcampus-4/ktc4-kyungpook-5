"""회의 후 화자 검토의 저장·복원. 외부 처리와 트랜잭션을 분리한다."""
from datetime import UTC, datetime
from pathlib import Path
import hashlib
import json
from typing import Protocol
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app import ai
from app.core.enums import (
    AgentJobKind, ContextDecisionStatus, ContextSourceType, JudgeKind, JudgeRoute,
    MeetingStatus, MemberStatus, TaskSuggestionStatus,
)
from app.core.exceptions import ApiError, IdempotencyConflict, VersionConflict
from app.models.agent import ContextDecision
from app.models.clubs import Member
from app.models.meetings import Meeting, TranscriptSegment
from app.models.meeting_review import MeetingReview
from app.models.tasks import TaskSuggestion
from app.services import agent_job_service


class ReviewConflict(ApiError):
    status_code = 409
    code = 'MEETING_REVIEW_CONFLICT'
    def __init__(self, message='회의 검토 상태가 바뀌었어요. 다시 확인해 주세요.'):
        super().__init__(message)


class DiarizationUnavailable(ApiError):
    status_code = 503
    code = 'DIARIZATION_UNAVAILABLE'

    def __init__(self, code='DIARIZATION_UNAVAILABLE', message='화자분리 서비스를 사용할 수 없어요. 원래 전사는 유지됩니다.'):
        self.code = code if code.startswith('DIARIZATION_') else 'DIARIZATION_UNAVAILABLE'
        super().__init__(message)


class DiarizationProvider(Protocol):
    async def submit(self, wav_path: Path) -> str: ...
    async def result(self, job_id: str, *, duration_ms: int) -> list[dict] | None: ...


async def start(session: AsyncSession, *, meeting: Meeting, member_id: str) -> MeetingReview:
    locked = await session.scalar(select(Meeting).where(Meeting.id == meeting.id).with_for_update())
    if locked.status != MeetingStatus.COMPLETED:
        raise ReviewConflict('종료된 회의만 검토할 수 있어요.')
    existing = await session.scalar(select(MeetingReview).where(MeetingReview.meeting_id == meeting.id))
    if existing is not None:
        return existing
    job = await agent_job_service.create_job(session, club_id=meeting.club_id,
                                             kind=AgentJobKind.MEETING_REVIEW, created_by=member_id)
    review = MeetingReview(meeting_id=meeting.id, job_id=job.id, status='QUEUED', version=1)
    session.add(review)
    await session.commit()
    return review


async def get(session: AsyncSession, meeting_id: str, *, lock: bool = False) -> MeetingReview | None:
    stmt = select(MeetingReview).where(or_(MeetingReview.meeting_id == meeting_id, MeetingReview.id == meeting_id))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def audio_snapshot(session: AsyncSession, meeting_id: str) -> list[tuple[int, int, str]]:
    """Provider adapter가 읽을 회의 음성 청크 순서·시간·저장 키만 반환한다.

    소속 확인과 실제 파일 읽기/무음 조립은 호출 서비스와 provider adapter가 담당한다.
    """
    from app.models.meetings import MeetingAudioChunk
    return list((await session.execute(select(MeetingAudioChunk.start_ms, MeetingAudioChunk.end_ms,
        MeetingAudioChunk.storage_key).where(MeetingAudioChunk.meeting_id == meeting_id)
        .order_by(MeetingAudioChunk.start_ms, MeetingAudioChunk.seq))).all())


def align_segments(segments, turns):
    """원문을 분할하지 않는다. 교차·중복 화자 구간은 미확인으로 둔다."""
    result = []
    for segment in segments:
        labels = set()
        if segment.start_ms is not None and segment.end_ms is not None:
            labels = {turn['speaker_label'] for turn in turns
                      if turn['start_ms'] < segment.end_ms and turn['end_ms'] > segment.start_ms}
        label = next(iter(labels)) if len(labels) == 1 else None
        result.append({'segmentId': segment.id, 'seq': segment.seq, 'text': segment.text,
                       'startMs': segment.start_ms, 'endMs': segment.end_ms, 'speakerLabel': label})
    return result


async def output(session: AsyncSession, review: MeetingReview) -> dict:
    segments = list(await session.scalars(select(TranscriptSegment).where(
        TranscriptSegment.meeting_id == review.meeting_id, TranscriptSegment.is_final.is_(True)
    ).order_by(TranscriptSegment.seq)))
    mappings = review.speaker_mappings or {}
    speakers = []
    for label in sorted({turn['speaker_label'] for turn in review.turns or []}):
        speaker = {'label': label, 'name': (review.speaker_names or {}).get(label)}
        mapping = mappings.get(label) or {}
        if mapping.get('memberId') is not None:
            speaker.update(memberId=mapping['memberId'], confirmed=bool(mapping.get('confirmed', False)))
        speakers.append(speaker)
    return {'id': review.id, 'meetingId': review.meeting_id, 'jobId': review.job_id,
            'status': review.status, 'version': review.version, 'errorCode': review.error_code,
            'speakers': speakers,
            'segments': align_segments(segments, review.turns or []), 'draft': review.draft}


async def set_names(
    session: AsyncSession,
    review: MeetingReview,
    version: int,
    names: dict[str, str],
    members: dict[str, dict[str, object]] | None = None,
):
    review = await get(session, review.meeting_id, lock=True)
    if review.version != version:
        raise VersionConflict()
    if review.status not in ('NEEDS_REVIEW', 'DRAFT_READY'):
        raise ReviewConflict()
    labels = {turn['speaker_label'] for turn in review.turns or []}
    if not set(names) <= labels:
        raise ReviewConflict('존재하지 않는 화자입니다.')
    members = members or {}
    if set(members) - labels or set(names) - labels:
        raise ReviewConflict('존재하지 않는 화자입니다.')
    member_ids = {
        value.get('memberId') for value in members.values()
        if isinstance(value, dict) and value.get('memberId')
    }
    rows = list(await session.scalars(select(Member).where(
        Member.id.in_(member_ids), Member.club_id == (await session.get(Meeting, review.meeting_id)).club_id,
        Member.status == MemberStatus.ACTIVE,
    ))) if member_ids else []
    by_id = {row.id: row for row in rows}
    if len(by_id) != len(member_ids):
        raise ReviewConflict('같은 동아리의 활성 구성원만 화자로 지정할 수 있어요.')
    if any(not isinstance(name, str) or not name.strip() for name in names.values()):
        raise ReviewConflict('화자 이름을 비워 둘 수 없습니다.')
    mapping: dict[str, dict[str, object]] = {}
    normalized_names: dict[str, str] = {}
    for label in labels:
        spec = members.get(label, {})
        member_id = spec.get('memberId') if isinstance(spec, dict) else None
        name = by_id[member_id].name if member_id else names.get(label)
        if name is None:
            continue
        if not isinstance(name, str) or not name.strip():
            raise ReviewConflict('화자 이름을 비워 둘 수 없습니다.')
        normalized_names[label] = name.strip()
        mapping[label] = {
            'memberId': member_id,
            'name': name.strip(),
            'confirmed': bool(spec.get('confirmed', False)) if isinstance(spec, dict) else True,
        }
    review.speaker_names = normalized_names
    review.speaker_mappings = mapping
    review.draft = None
    review.status = 'NEEDS_REVIEW'
    review.version += 1
    await session.commit()
    return review


def _candidate_hash(candidates: list[dict[str, object]]) -> str:
    payload = json.dumps(candidates, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


async def save_candidates(
    session: AsyncSession,
    *,
    review_id: str,
    expected_version: int,
    client_request_id: str,
    candidates: list[dict[str, object]],
    confirmed_by: str,
) -> list[TaskSuggestion]:
    review = await session.scalar(select(MeetingReview).where(MeetingReview.id == review_id).with_for_update())
    if review is None:
        raise ReviewConflict('회의 검토를 찾을 수 없습니다.')
    fingerprint = _candidate_hash(candidates)
    if review.candidate_request_id:
        if review.candidate_request_id != client_request_id or review.candidate_hash != fingerprint:
            raise IdempotencyConflict()
        ids = review.candidate_ids or []
        return list(await session.scalars(select(TaskSuggestion).where(TaskSuggestion.id.in_(ids)))) if ids else []
    if review.version != expected_version:
        raise VersionConflict()
    if review.status not in ('NEEDS_REVIEW', 'DRAFT_READY'):
        raise ReviewConflict('화자분리와 회의록 검토가 끝난 뒤 후보를 저장할 수 있어요.')
    meeting = await session.get(Meeting, review.meeting_id)
    if meeting is None:
        raise ReviewConflict('회의를 찾을 수 없습니다.')
    evidence_ids = {item for candidate in candidates for item in candidate.get('evidence_segment_ids', [])}
    segments = list(await session.scalars(select(TranscriptSegment).where(
        TranscriptSegment.meeting_id == meeting.id,
        TranscriptSegment.id.in_(evidence_ids),
        TranscriptSegment.is_final.is_(True),
    ))) if evidence_ids else []
    by_id = {segment.id: segment for segment in segments}
    if len(by_id) != len(evidence_ids):
        raise ReviewConflict('같은 회의의 확정 전사만 근거로 사용할 수 있어요.')
    member_ids = {item.get('assignee_member_id') for item in candidates if item.get('assignee_member_id')}
    members = list(await session.scalars(select(Member).where(
        Member.id.in_(member_ids), Member.club_id == meeting.club_id, Member.status == MemberStatus.ACTIVE,
    ))) if member_ids else []
    member_by_id = {member.id: member for member in members}
    if len(member_by_id) != len(member_ids):
        raise ReviewConflict('같은 동아리의 활성 구성원만 담당자로 지정할 수 있어요.')
    decision = await session.scalar(select(ContextDecision).where(ContextDecision.job_id == review.job_id).with_for_update())
    if decision is None:
        sources = [
            {'sourceId': segment.id, 'sourceVersion': segment.version}
            for segment in segments
        ]
        decision = ContextDecision(
            club_id=meeting.club_id, job_id=review.job_id, source_type=ContextSourceType.MEETING_TRANSCRIPT,
            meeting_id=meeting.id, sources=sources, status=ContextDecisionStatus.SUCCEEDED,
            route=JudgeRoute.LLM, kind=JudgeKind.ANSWER, reason_summary='회의 종료 검토 후보',
            tool_calls=[], model_version='meeting-review', policy_version='meeting-review-v1',
        )
        session.add(decision)
        await session.flush()
    created: list[TaskSuggestion] = []
    for candidate in candidates:
        evidence = [
            {'sourceId': item, 'sourceVersion': by_id[item].version}
            for item in candidate.get('evidence_segment_ids', [])
        ]
        assignee_id = candidate.get('assignee_member_id')
        member = member_by_id.get(assignee_id) if assignee_id else None
        created.append(TaskSuggestion(
            club_id=meeting.club_id, decision_id=decision.id, source_type=ContextSourceType.MEETING_TRANSCRIPT,
            title=str(candidate.get('title', '')).strip(), description=candidate.get('description'),
            suggested_assignee=member.name if member else None,
            suggested_assignee_member_id=assignee_id, due_date=candidate.get('due_date'), kind='TASK',
            unresolved_fields=[] if candidate.get('due_date') and member else [
                field for field, value in (('dueDate', candidate.get('due_date')), ('assignee', member)) if not value
            ], evidence=evidence, status=TaskSuggestionStatus.ACCEPTED,
            accepted_by=confirmed_by,
            accepted_at=datetime.now(UTC),
        ))
    session.add_all(created)
    await session.flush()
    review.candidate_request_id = client_request_id
    review.candidate_hash = fingerprint
    review.candidate_ids = [item.id for item in created]
    review.version += 1
    await session.commit()
    return created


async def fail_diarization(session: AsyncSession, review_id: str, *, error_code: str) -> MeetingReview:
    review = await session.scalar(select(MeetingReview).where(MeetingReview.id == review_id).with_for_update())
    if review is None:
        raise ReviewConflict()
    if review.status in ('PROCESSING', 'SUBMITTING'):
        review.status = 'FAILED'
        review.error_code = error_code
        review.version += 1
        await session.commit()
    return review


async def apply_diarization(session: AsyncSession, review_id: str, *, provider_job_id: str,
                            turns: list[dict], duration_ms: int | None = None):
    review = await session.scalar(select(MeetingReview).where(MeetingReview.id == review_id)
                                  .with_for_update().execution_options(populate_existing=True))
    if review is None or review.status != 'PROCESSING' or review.provider_job_id != provider_job_id:
        raise ReviewConflict('화자분리 작업 상태가 바뀌었어요.')
    valid = []
    previous_end = -1
    for turn in turns:
        start, end, label = turn.get('start_ms'), turn.get('end_ms'), turn.get('speaker_label')
        if not isinstance(start, int) or not isinstance(end, int) or end <= start or not isinstance(label, str) or not label.strip():
            raise ReviewConflict('화자분리 결과 형식이 올바르지 않아요.')
        # overlapping turns are retained as provider evidence; alignment marks them unknown.
        valid.append({'start_ms': start, 'end_ms': end, 'speaker_label': label})
        previous_end = max(previous_end, end)
    review.provider_job_id = provider_job_id
    review.turns = valid
    review.duration_ms = duration_ms
    review.status = 'NEEDS_REVIEW'
    review.version += 1
    await session.commit()
    return review


async def submit_diarization(session: AsyncSession, review_id: str, *, wav_path: Path,
                             provider: DiarizationProvider):
    """제출 직후 provider job ID를 저장한다. WAV 조립은 호출 adapter가 담당한다."""
    review = await session.scalar(select(MeetingReview).where(MeetingReview.id == review_id)
                                  .with_for_update().execution_options(populate_existing=True))
    if review is None or review.status != 'QUEUED' or review.provider_job_id:
        raise ReviewConflict('화자분리 작업을 시작할 수 없어요.')
    review.status = 'SUBMITTING'
    review.version += 1
    await session.commit()
    try:
        provider_job_id = await provider.submit(wav_path)
    except Exception as error:
        review = await session.scalar(select(MeetingReview).where(MeetingReview.id == review_id)
                                      .with_for_update().execution_options(populate_existing=True))
        review.status = 'SUBMISSION_UNKNOWN'
        review.error_code = getattr(error, 'code', None) or type(error).__name__
        review.version += 1
        await session.commit()
        raise
    review = await session.scalar(select(MeetingReview).where(MeetingReview.id == review_id)
                                  .with_for_update().execution_options(populate_existing=True))
    if review is None or review.status != 'SUBMITTING':
        raise ReviewConflict('화자분리 제출 상태가 바뀌었어요.')
    review.provider_job_id = provider_job_id
    review.status = 'PROCESSING'
    review.version += 1
    await session.commit()
    return review


async def poll_diarization(session: AsyncSession, review_id: str, *, duration_ms: int,
                           provider: DiarizationProvider):
    review = await session.scalar(select(MeetingReview).where(MeetingReview.id == review_id)
                                  .with_for_update().execution_options(populate_existing=True))
    if review is None or review.status != 'PROCESSING' or not review.provider_job_id:
        raise ReviewConflict('진행 중인 화자분리 작업이 없어요.')
    provider_job_id = review.provider_job_id
    await session.commit()
    turns = await provider.result(provider_job_id, duration_ms=duration_ms)
    if turns is None:
        return await session.get(MeetingReview, review_id)
    return await apply_diarization(session, review_id, provider_job_id=provider_job_id,
                                   turns=turns, duration_ms=duration_ms)


async def generate_draft(session: AsyncSession, review: MeetingReview, version: int):
    review = await get(session, review.meeting_id, lock=True)
    if review.version != version or review.status != 'NEEDS_REVIEW':
        raise ReviewConflict()
    segments = list(await session.scalars(select(TranscriptSegment).where(
        TranscriptSegment.meeting_id == review.meeting_id, TranscriptSegment.is_final.is_(True),
        TranscriptSegment.text != ''
    ).order_by(TranscriptSegment.seq)))
    aligned = align_segments(segments, review.turns or [])
    names = review.speaker_names or {}
    request = ai.MeetingReviewRequest(transcripts=tuple(ai.ReviewTranscript(
        segment_id=row['segmentId'], text=row['text'], speaker_label=row['speakerLabel'],
        speaker_name=names.get(row['speakerLabel'])) for row in aligned))
    review_id, meeting_id = review.id, review.meeting_id
    await session.commit()
    draft = await ai.generate_meeting_review(request)
    review = await get(session, meeting_id, lock=True)
    if review.id != review_id or review.version != version or review.status != 'NEEDS_REVIEW':
        raise ReviewConflict()
    review.draft = draft.model_dump(mode='json')
    review.status = 'DRAFT_READY'
    review.version += 1
    await session.commit()
    return review
