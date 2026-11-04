import type { components } from '@/shared/api/schema'
type S = components['schemas']
export type Meeting = S['MeetingOut']
export type Transcript = S['TranscriptSegmentOut']
export type TranscriptList = S['TranscriptListOut']
export type Decision = S['ContextDecisionOut']
export type Suggestion = S['TaskSuggestionOut']
export type Job = S['AgentJobOut']

export type MeetingReview = {
  id: string
  meetingId: string
  jobId: string
  status: string
  version: number
  errorCode: string | null
  speakers: { label: string; name: string | null }[]
  segments: { segmentId: string; seq: number; text: string; startMs: number | null; endMs: number | null; speakerLabel: string | null }[]
  draft: { summary: { text: string; evidenceSegmentIds: string[] }[]; tasks: { title: string; suggestedAssignee: string | null; evidenceSegmentIds: string[] }[] } | null
}
