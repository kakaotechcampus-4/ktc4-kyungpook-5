import type { components } from '@/shared/api/schema'
type S = components['schemas']
export type Meeting = S['MeetingOut']
export type Transcript = S['TranscriptSegmentOut']
export type TranscriptList = S['TranscriptListOut']
export type Decision = S['ContextDecisionOut']
export type Suggestion = S['TaskSuggestionOut']
export type Job = S['AgentJobOut']

export type MeetingReviewSpeaker = { label: string; name: string | null; memberId?: string | null; confirmed?: boolean }
export type MeetingReviewSegment = { segmentId: string; seq: number; text: string; startMs: number | null; endMs: number | null; speakerLabel: string | null }
export type MeetingReviewTask = { title: string; description: string | null; suggestedAssignee: string | null; suggestedAssigneeMemberId: string | null; dueDate: string | null; evidenceSegmentIds: string[] }
export type MeetingReview = {
  id: string; meetingId: string; jobId: string; status: string; version: number; errorCode: string | null
  speakers: MeetingReviewSpeaker[]; segments: MeetingReviewSegment[]
  draft: { summary: { text: string; evidenceSegmentIds: string[] }[]; tasks: MeetingReviewTask[] } | null
}
