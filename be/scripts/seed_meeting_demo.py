"""Create or remove one explicitly requested golden-path demo fixture.

This is an operator-invoked one-shot command, not an application route or migration.
It never handles passwords, access tokens, or AI/provider calls. The fixture contains
two indexed CSV records, one completed meeting, a transcript, and a proposed task
candidate so the beta flow can be repeated without depending on provider availability.

Examples::

    python scripts/seed_meeting_demo.py --account-id acc_... --manager-account-id acc_... --club-id clb_...
    python scripts/seed_meeting_demo.py --account-id acc_... --manager-account-id acc_... --club-id clb_... --apply
    python scripts/seed_meeting_demo.py --account-id acc_... --manager-account-id acc_... --club-id clb_... --rollback
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, date, datetime

from sqlalchemy import delete, select

from app import ai
from app.core.enums import (
    AgentJobKind,
    AgentJobStatus,
    ContextDecisionStatus,
    ContextSourceType,
    JudgeKind,
    JudgeRoute,
    MemberStatus,
    MeetingStatus,
    RecordCategory,
    RecordFileType,
    RecordParseStatus,
    SERVICE_ROLES,
    TaskSuggestionStatus,
)
from app.db.session import get_sessionmaker
from app.infra.storage import delete_file, save_file
from app.models.agent import AgentJob, ContextDecision
from app.models.clubs import Member
from app.models.meetings import Meeting, TranscriptSegment
from app.models.record_chunks import RecordChunk
from app.models.records import Record
from app.services.record_parser import parse_record
from app.models.tasks import TaskSuggestion


_DEMO_RECORDS = (
    (
        "MT 예산.csv",
        "항목,금액\n숙소,550000\n교통,300000\n식비,250000\n".encode(),
        RecordCategory.LEDGER,
    ),
    (
        "MT 일정.csv",
        "일정,내용\n장소 예약,다음 주 토요일\n참석 인원 확인,금요일까지\n".encode(),
        RecordCategory.EVENT_HISTORY,
    ),
)


def _demo_embedding() -> list[float]:
    """Return a deterministic valid vector without calling an embedding provider."""

    return [1.0] + [0.0] * (ai.EMBEDDING_DIMENSIONS - 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument(
        "--manager-account-id",
        default=None,
        help="같은 소속의 두 번째 활성 OWNER/MANAGER 계정. 골든 패스 확인용.",
    )
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


async def _second_member(
    session, *, account_id: str, club_id: str, first_member: Member
) -> Member:
    if account_id == first_member.account_id:
        raise SystemExit("manager-account-id는 account-id와 다른 운영진 계정이어야 합니다.")
    member = await session.scalar(
        select(Member).where(
            Member.account_id == account_id,
            Member.club_id == club_id,
            Member.status == MemberStatus.ACTIVE,
            Member.role.in_(SERVICE_ROLES),
        )
    )
    if member is None:
        raise SystemExit("manager-account-id가 해당 club_id의 활성 OWNER/MANAGER 소속이 아닙니다.")
    return member


async def _existing(session, *, club_id: str, demo_key: str) -> Meeting | None:
    return await session.scalar(select(Meeting).where(
        Meeting.club_id == club_id,
        Meeting.title == f"{marker(demo_key)} 운영 회의 확인",
    ))


async def _existing_records(session, *, club_id: str, demo_key: str) -> list[Record]:
    return list(
        await session.scalars(
            select(Record)
            .where(
                Record.club_id == club_id,
                Record.file_name.like(f"{marker(demo_key)}%"),
            )
            .order_by(Record.file_name)
        )
    )


async def _plan(
    session,
    *,
    args: argparse.Namespace,
    member: Member,
    manager: Member | None,
) -> dict[str, object]:
    existing = await _existing(session, club_id=args.club_id, demo_key=args.demo_key)
    records = await _existing_records(session, club_id=args.club_id, demo_key=args.demo_key)
    if existing is not None or records:
        return {
            "action": "noop",
            "meetingId": existing.id if existing else None,
            "recordIds": [record.id for record in records],
            "demoKey": args.demo_key,
            "reason": "같은 demo-key fixture가 이미 있습니다. 먼저 --rollback 하세요.",
        }
    return {
        "action": "create",
        "clubId": args.club_id,
        "accountId": args.account_id,
        "createdByMemberId": member.id,
        "secondOperatorMemberId": manager.id if manager else None,
        "demoKey": args.demo_key,
        "title": f"{marker(args.demo_key)} 운영 회의 확인",
        "status": MeetingStatus.COMPLETED.value,
        "transcript": args.transcript,
        "dueDate": args.due_date.isoformat() if args.due_date else None,
        "creates": [
            "2 indexed CSV records",
            "meeting",
            "confirmed transcript",
            "ContextDecision with record evidence",
            "TaskSuggestion(PROPOSED)",
        ],
        "createsNo": [
            "password",
            "token",
            "AI/provider call",
            "TaskReminder",
            "PushSubscription",
            "Push delivery",
        ],
    }


async def apply_create(session, *, args: argparse.Namespace, member: Member) -> dict[str, object]:
    existing = await _existing(session, club_id=args.club_id, demo_key=args.demo_key)
    records = await _existing_records(session, club_id=args.club_id, demo_key=args.demo_key)
    if existing is not None or records:
        return {
            "action": "noop",
            "meetingId": existing.id if existing else None,
            "recordIds": [record.id for record in records],
            "demoKey": args.demo_key,
        }
    storage_keys: list[str] = []
    created_records: list[Record] = []
    try:
        for file_name, content, category in _DEMO_RECORDS:
            full_name = f"{marker(args.demo_key)} {file_name}"
            storage_key = save_file(args.club_id, full_name, content)
            storage_keys.append(storage_key)
            parse_result = parse_record(content, RecordFileType.CSV)
            record = Record(
                club_id=args.club_id,
                file_name=full_name,
                file_type=RecordFileType.CSV,
                category=category,
                storage_key=storage_key,
                size=len(content),
                parse_status=RecordParseStatus.INDEXED,
                parse_result=parse_result,
            )
            session.add(record)
            await session.flush()
            created_records.append(record)
            session.add_all(
                [
                    RecordChunk(
                        record_id=record.id,
                        chunk_index=index,
                        text=block["text"],
                        location=block["location"],
                        block_indexes=[index],
                        embedding=_demo_embedding(),
                    )
                    for index, block in enumerate(parse_result["blocks"])
                ]
            )
        await session.flush()
        citations = [
            {
                "recordId": record.id,
                "fileName": record.file_name,
                "location": block["location"],
            }
            for record in created_records
            for block in (record.parse_result or {}).get("blocks", [])
        ]
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
            question=args.transcript,
            output="자료에서 장소 예약과 참석 인원 확인 일정을 찾았습니다.",
            citations=citations,
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
    except Exception:
        await session.rollback()
        for storage_key in storage_keys:
            try:
                delete_file(storage_key)
            except Exception:
                # The original error is more useful than a cleanup failure. Operators
                # can remove an orphaned object with the printed demo-key if necessary.
                pass
        raise
    return {
        "action": "created",
        "meetingId": meeting.id,
        "recordIds": [record.id for record in created_records],
        "transcriptId": segment.id,
        "taskSuggestionId": suggestion.id,
        "demoKey": args.demo_key,
    }


async def rollback(session, *, args: argparse.Namespace) -> dict[str, object]:
    meeting = await _existing(session, club_id=args.club_id, demo_key=args.demo_key)
    records = await _existing_records(session, club_id=args.club_id, demo_key=args.demo_key)
    if meeting is None and not records:
        return {"action": "noop", "demoKey": args.demo_key}
    storage_keys = [record.storage_key for record in records]
    if meeting is not None:
        decisions = list(
            await session.scalars(
                select(ContextDecision).where(ContextDecision.meeting_id == meeting.id)
            )
        )
        decision_ids = [item.id for item in decisions]
        if decision_ids:
            await session.execute(
                delete(TaskSuggestion).where(TaskSuggestion.decision_id.in_(decision_ids))
            )
        await session.execute(delete(ContextDecision).where(ContextDecision.meeting_id == meeting.id))
        await session.execute(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting.id))
        await session.execute(
            delete(AgentJob).where(
                AgentJob.club_id == args.club_id,
                AgentJob.result["demoKey"].as_string() == args.demo_key,
            )
        )
        await session.execute(delete(Meeting).where(Meeting.id == meeting.id))
    if records:
        record_ids = [record.id for record in records]
        await session.execute(delete(RecordChunk).where(RecordChunk.record_id.in_(record_ids)))
        await session.execute(delete(Record).where(Record.id.in_(record_ids)))
    await session.commit()
    for storage_key in storage_keys:
        delete_file(storage_key)
    return {
        "action": "rolled_back",
        "meetingId": meeting.id if meeting else None,
        "recordIds": [record.id for record in records],
        "demoKey": args.demo_key,
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    async with get_sessionmaker()() as session:
        member = await _member(session, account_id=args.account_id, club_id=args.club_id)
        if args.rollback:
            return await rollback(session, args=args)
        manager = None
        if args.manager_account_id:
            manager = await _second_member(
                session,
                account_id=args.manager_account_id,
                club_id=args.club_id,
                first_member=member,
            )
        plan = await _plan(session, args=args, member=member, manager=manager)
        if not args.apply:
            return {**plan, "dryRun": True}
        return await apply_create(session, args=args, member=member)


def main() -> None:
    args = build_parser().parse_args()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.demo_key) is None:
        raise SystemExit("demo-key는 영문·숫자·.-로 된 1~64자의 식별자여야 합니다.")
    print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
