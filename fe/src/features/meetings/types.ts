import type { components } from '@/shared/api/schema'
type S = components['schemas']
export type Meeting = S['MeetingOut']
export type Transcript = S['TranscriptSegmentOut']
export type TranscriptList = S['TranscriptListOut']
export type Decision = S['ContextDecisionOut']
export type Suggestion = S['TaskSuggestionOut']
export type Job = S['AgentJobOut']
export type TimelineEntry = { type: 'transcript'; id: string } | { type: 'decision'; id: string }
