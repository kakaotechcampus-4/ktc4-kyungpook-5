"""Create or remove one explicitly requested demo meeting.

This is an operator-invoked one-shot command, not an application route or migration.
It never handles passwords, access tokens, or AI/provider calls.

Examples::

    python scripts/seed_meeting_demo.py --account-id acc_... --club-id clb_...
    python scripts/seed_meeting_demo.py --account-id acc_... --club-id clb_... --apply
    python scripts/seed_meeting_demo.py --account-id acc_... --club-id clb_... --rollback
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, date, datetime

from sqlalchemy import delete, select

from app.core.enums import (
    AgentJobKind,
    AgentJobStatus,
    ContextDecisionStatus,
    ContextSourceType,
    JudgeKind,
    JudgeRoute,
    MemberStatus,
    MeetingStatus,
    SERVICE_ROLES,
    TaskSuggestionStatus,
)
from app.db.session import get_sessionmaker
from app.models.agent import AgentJob, ContextDecision
from app.models.clubs import Member
from app.models.meetings import Meeting, TranscriptSegment
from app.models.tasks import TaskSuggestion


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--club-id", required=True)
    parser.add_argument("--demo-key", default="meeting-beta-1")
    parser.add_argument(
        "--transcript",
        default="다음 주 토요일까지 장소를 예약하고 참석 인원을 확인합니다.",
    )
    parser.add_argument("--due-date", type=date.fromisoformat, default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="기본값. 권한·중복·입력만 확인하고 저장하지 않습니다.")
    mode.add_argument("--apply", action="store_true", help="검증 후 실제로 한 건을 저장합니다.")
    mode.add_argument("--rollback", action="store_true", help="같은 demo-key로 만든 자료만 삭제합니다.")
    return parser


def marker(demo_key: str) -> str:
    return f"[DEMO:{demo_key}]"


async def _member(session, *, account_id: str, club_id: str) -> Member:
    member = await session.scalar(select(Member).where(
        Member.account_id == account_id,
        Member.club_id == club_id,
        Member.status == MemberStatus.ACTIVE,
        Member.role.in_(SERVICE_ROLES),
    ))
    if member is None:
        raise SystemExit("account_id가 해당 club_id의 활성 OWNER/MANAGER 소속이 아닙니다.")
    return member


async def _existing(session, *, club_id: str, demo_key: str) -> Meeting | None:
    return await session.scalar(select(Meeting).where(
        Meeting.club_id == club_id,
        Meeting.title == f"{marker(demo_key)} 운영 회의 확인",
    ))


async def _plan(session, *, args: argparse.Namespace, member: Member) -> dict[str, object]:
    existing = await _existing(session, club_id=args.club_id, demo_key=args.demo_key)
    if existing is not None:
        return {"action": "noop", "meetingId": existing.id, "demoKey": args.demo_key}
    return {
        "action": "create",
        "clubId": args.club_id,
        "accountId": args.account_id,
        "createdByMemberId": member.id,
        "demoKey": args.demo_key,
        "title": f"{marker(args.demo_key)} 운영 회의 확인",
        "status": MeetingStatus.COMPLETED.value,
        "transcript": args.transcript,
        "dueDate": args.due_date.isoformat() if args.due_date else None,
        "creates": ["meeting", "confirmed transcript", "TaskSuggestion(PROPOSED)"],
        "createsNo": ["password", "token", "TaskReminder", "PushSubscription", "Push delivery"],
    }


async def apply_create(session, *, args: argparse.Namespace, member: Member) -> dict[str, object]:
    existing = await _existing(session, club_id=args.club_id, demo_key=args.demo_key)
    if existing is not None:
        return {"action": "noop", "meetingId": existing.id, "demoKey": args.demo_key}
    now = datetime.now(UTC)
    meeting = Meeting(
        club_id=args.club_id,
        title=f"{marker(args.demo_key)} 운영 회의 확인",
        language="ko-KR",
        status=MeetingStatus.COMPLETED,
        started_at=now,
        ended_at=now,
        recording_consent_confirmed_by=member.id,
        recording_consent_confirmed_at=now,
        created_by=member.id,
    )
    session.add(meeting)
    await session.flush()
    stt_job = AgentJob(
        club_id=args.club_id, kind=AgentJobKind.MEETING_STT,
        status=AgentJobStatus.SUCCEEDED, created_by=member.id,
        result={"demoKey": args.demo_key, "source": "operator-one-shot"},
    )
    session.add(stt_job)
    await session.flush()
    segment = TranscriptSegment(
        meeting_id=meeting.id, seq=1, text=args.transcript, is_final=True,
        version=1, change_seq=1, start_ms=0, end_ms=1000,
    )
    session.add(segment)
    await session.flush()
    decision_job = AgentJob(
        club_id=args.club_id, kind=AgentJobKind.CONTEXT_DECISION,
        status=AgentJobStatus.SUCCEEDED, created_by=member.id,
        result={"demoKey": args.demo_key, "source": "operator-one-shot"},
    )
    session.add(decision_job)
    await session.flush()
    segment.decision_job_id = decision_job.id
    decision = ContextDecision(
        club_id=args.club_id, job_id=decision_job.id,
        source_type=ContextSourceType.MEETING_TRANSCRIPT, meeting_id=meeting.id,
        sources=[{"sourceId": segment.id, "sourceVersion": segment.version}],
        status=ContextDecisionStatus.SUCCEEDED, route=JudgeRoute.LLM,
        kind=JudgeKind.ANSWER, reason_summary="운영자 데모 후보",
        tool_calls=[], model_version="operator-one-shot", policy_version="demo-v1",
    )
    session.add(decision)
    await session.flush()
    suggestion = TaskSuggestion(
        club_id=args.club_id, decision_id=decision.id,
        source_type=ContextSourceType.MEETING_TRANSCRIPT,
        title="회의 후 장소 예약 확인", description="사용자가 내용을 확인한 뒤 예약합니다.",
        suggested_assignee=member.name, suggested_assignee_member_id=member.id,
        due_date=args.due_date, kind="TASK", unresolved_fields=[] if args.due_date else ["dueDate"],
        evidence=[{"sourceId": segment.id, "sourceVersion": segment.version}],
        status=TaskSuggestionStatus.PROPOSED,
    )
    session.add(suggestion)
    await session.commit()
    return {
        "action": "created", "meetingId": meeting.id, "transcriptId": segment.id,
        "taskSuggestionId": suggestion.id, "demoKey": args.demo_key,
    }


async def rollback(session, *, args: argparse.Namespace) -> dict[str, object]:
    meeting = await _existing(session, club_id=args.club_id, demo_key=args.demo_key)
    if meeting is None:
        return {"action": "noop", "demoKey": args.demo_key}
    decisions = list(await session.scalars(select(ContextDecision).where(ContextDecision.meeting_id == meeting.id)))
    decision_ids = [item.id for item in decisions]
    if decision_ids:
        await session.execute(delete(TaskSuggestion).where(TaskSuggestion.decision_id.in_(decision_ids)))
    await session.execute(delete(ContextDecision).where(ContextDecision.meeting_id == meeting.id))
    await session.execute(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting.id))
    await session.execute(delete(AgentJob).where(
        AgentJob.club_id == args.club_id,
        AgentJob.result["demoKey"].as_string() == args.demo_key,
    ))
    await session.execute(delete(Meeting).where(Meeting.id == meeting.id))
    await session.commit()
    return {"action": "rolled_back", "meetingId": meeting.id, "demoKey": args.demo_key}


async def run(args: argparse.Namespace) -> dict[str, object]:
    async with get_sessionmaker()() as session:
        member = await _member(session, account_id=args.account_id, club_id=args.club_id)
        if args.rollback:
            return await rollback(session, args=args)
        plan = await _plan(session, args=args, member=member)
        if not args.apply:
            return {**plan, "dryRun": True}
        return await apply_create(session, args=args, member=member)


def main() -> None:
    args = build_parser().parse_args()
    if args.demo_key != args.demo_key.strip() or not args.demo_key or len(args.demo_key) > 64:
        raise SystemExit("demo-key는 1~64자의 공백 없는 식별자여야 합니다.")
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
