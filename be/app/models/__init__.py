"""ORM 모델.

Base.metadata가 모든 테이블을 알도록 여기서 전부 import한다.
새 모델을 추가하면 이 파일에도 등록한다.
"""

from app.db.base import Base
from app.models.accounting import Expense, ReceiptImport, ReceiptImportRow
from app.models.agent import ActivityEvent, AgentJob, AgentLog, ContextDecision
from app.models.auth import Account, Auth
from app.models.chat import Conversation, Message
from app.models.clubs import Club, Invitation, Member
from app.models.common import IdempotencyKey
from app.models.discord import DiscordConnection, DiscordMessage
from app.models.events import Action, Event, Participant, Step
from app.models.meetings import Meeting, MeetingAudioChunk, TranscriptSegment
from app.models.records import Record, RecordChunk
from app.models.tasks import TaskSuggestion

__all__ = [
    "Account",
    "Action",
    "ActivityEvent",
    "AgentJob",
    "AgentLog",
    "Auth",
    "Base",
    "Club",
    "ContextDecision",
    "Conversation",
    "DiscordConnection",
    "DiscordMessage",
    "Event",
    "Expense",
    "IdempotencyKey",
    "Invitation",
    "Meeting",
    "MeetingAudioChunk",
    "Member",
    "Message",
    "Participant",
    "Record",
    "ReceiptImport",
    "ReceiptImportRow",
    "Step",
    "TaskSuggestion",
    "TranscriptSegment",
]
