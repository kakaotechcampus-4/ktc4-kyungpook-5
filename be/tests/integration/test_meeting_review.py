"""회의 종료 후 검토 상태, 화자 이름과 겹침 경계를 검증한다."""
from datetime import UTC, datetime
import pytest
from sqlalchemy import select
from app.core.enums import MeetingStatus, MemberRole
from app.db import session as db_session
from app.models.clubs import Club, Member
from app.models.meetings import Meeting, TranscriptSegment
from app.models.reminders import ConfirmedTask, TaskReminder
from app.core.exceptions import IdempotencyConflict, VersionConflict
from app.services import meeting_review_service, meeting_service
pytestmark = [pytest.mark.db, pytest.mark.anyio]
@pytest.fixture
async def app_db(migrated_db_url, monkeypatch, clear_db_caches):
    monkeypatch.setenv('DATABASE_URL', migrated_db_url); yield
    await db_session.get_engine().dispose()
async def seed(session):
    club = Club(name='검토 동아리'); session.add(club); await session.flush()
    member = Member(club_id=club.id, name='회장', role=MemberRole.OWNER); session.add(member); await session.flush()
    meeting = await meeting_service.create_meeting(session, club_id=club.id, event_id=None, title='종료 회의', language='ko-KR', recording_consent_confirmed=True, created_by=member.id)
    meeting.status = MeetingStatus.COMPLETED; meeting.ended_at = datetime.now(UTC)
    session.add(TranscriptSegment(meeting_id=meeting.id, seq=1, text='민수가 장소를 예약하자.', is_final=True, version=1, change_seq=1, start_ms=0, end_ms=1000))
    await session.commit(); return member.id, meeting.id
async def test_review_state_and_names_restore_without_confirming_tasks(app_db):
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        member_id, meeting_id = await seed(session); meeting = await session.get(Meeting, meeting_id)
        review = await meeting_review_service.start(session, meeting=meeting, member_id=member_id)
        review.status = 'PROCESSING'; review.provider_job_id = 'provider-job-1'; await session.commit()
        review = await meeting_review_service.apply_diarization(session, review.id, provider_job_id='provider-job-1', turns=[{'start_ms':0,'end_ms':1000,'speaker_label':'SPEAKER_00'}])
        review = await meeting_review_service.set_names(session, review, review.version, {'SPEAKER_00':'민수'})
        result = await meeting_review_service.output(session, review)
        assert result['speakers'] == [{'label':'SPEAKER_00','name':'민수'}]
        assert result['segments'][0]['speakerLabel'] == 'SPEAKER_00'
async def test_overlap_is_unknown_and_stale_version_rejected(app_db):
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        member_id, meeting_id = await seed(session); meeting = await session.get(Meeting, meeting_id)
        review = await meeting_review_service.start(session, meeting=meeting, member_id=member_id)
        review.status = 'PROCESSING'; review.provider_job_id = 'provider-job-2'; await session.commit()
        review = await meeting_review_service.apply_diarization(session, review.id, provider_job_id='provider-job-2', turns=[{'start_ms':0,'end_ms':800,'speaker_label':'SPEAKER_00'},{'start_ms':500,'end_ms':1000,'speaker_label':'SPEAKER_01'}])
        output = await meeting_review_service.output(session, review)
        assert output['segments'][0]['speakerLabel'] is None
        with pytest.raises(meeting_review_service.ReviewConflict):
            await meeting_review_service.set_names(session, review, review.version - 1, {'SPEAKER_00':'민수'})


async def test_speaker_member_mapping_and_candidate_save_are_confirmed_without_reminder(app_db):
    factory = db_session.get_sessionmaker()
    async with factory() as session:
        member_id, meeting_id = await seed(session)
        meeting = await session.get(Meeting, meeting_id)
        review = await meeting_review_service.start(session, meeting=meeting, member_id=member_id)
        review.status = 'NEEDS_REVIEW'
        review.turns = [{'start_ms': 0, 'end_ms': 1000, 'speaker_label': 'SPEAKER_00'}]
        await session.commit()
        review = await meeting_review_service.set_names(
            session, review, review.version, {},
            {'SPEAKER_00': {'memberId': member_id, 'confirmed': True}},
        )
        output = await meeting_review_service.output(session, review)
        assert output['speakers'][0]['memberId'] == member_id
        assert output['speakers'][0]['confirmed'] is True
        segment = await session.scalar(select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id))
        candidates = [{
            'title': '장소 예약', 'description': '숙소를 예약한다',
            'assignee_member_id': member_id, 'due_date': None,
            'evidence_segment_ids': [segment.id],
        }]
        saved = await meeting_review_service.save_candidates(
            session, review_id=review.id, expected_version=review.version,
            client_request_id='review-candidates-1', candidates=candidates, confirmed_by=member_id,
        )
        replay = await meeting_review_service.save_candidates(
            session, review_id=review.id, expected_version=1,
            client_request_id='review-candidates-1', candidates=candidates, confirmed_by=member_id,
        )
        assert [item.id for item in replay] == [saved[0].id]
        assert saved[0].status.value == 'ACCEPTED'
        assert saved[0].suggested_assignee_member_id == member_id
        assert not list(await session.scalars(select(ConfirmedTask)))
        assert not list(await session.scalars(select(TaskReminder)))
        with pytest.raises(IdempotencyConflict):
            await meeting_review_service.save_candidates(
                session, review_id=review.id, expected_version=review.version,
                client_request_id='review-candidates-1', candidates=[{**candidates[0], 'title': '다른 제목'}],
                confirmed_by=member_id,
            )
        with pytest.raises(VersionConflict):
            await meeting_review_service.set_names(
                session, review, review.version - 1, {},
                {'SPEAKER_00': {'memberId': member_id, 'confirmed': True}},
            )
