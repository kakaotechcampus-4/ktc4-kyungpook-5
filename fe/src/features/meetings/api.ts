import { apiGet, apiPatch, apiPost } from '@/shared/api/client'
import type { Decision, Job, Meeting, Suggestion, TranscriptList } from './types'
const id = encodeURIComponent
export const meetingsApi = {
  create: (clubId: string, title: string) =>
    apiPost<Meeting>(`/clubs/${id(clubId)}/meetings`, {
      title,
      language: 'ko-KR',
      recordingConsentConfirmed: true,
    }),
  get: (meetingId: string) => apiGet<Meeting>(`/meetings/${id(meetingId)}`),
  // afterSeq is a change cursor, never the last utterance seq or audio frame seq.
  transcripts: (meetingId: string) =>
    apiGet<TranscriptList>(`/meetings/${id(meetingId)}/transcripts?afterSeq=0`),
  decisions: (clubId: string, meetingId: string) =>
    apiGet<Decision[]>(
      `/clubs/${id(clubId)}/context-decisions?sourceType=MEETING_TRANSCRIPT&meetingId=${id(meetingId)}`,
    ),
  suggestions: (clubId: string) =>
    apiGet<Suggestion[]>(`/clubs/${id(clubId)}/task-suggestions?sourceType=MEETING_TRANSCRIPT`),
  job: (jobId: string) => apiGet<Job>(`/agent-jobs/${id(jobId)}`),
  finish: (meetingId: string) => apiPost<Meeting>(`/meetings/${id(meetingId)}/finish`),
  patchSuggestion: (
    clubId: string,
    suggestion: Suggestion,
    values: {
      title: string
      description: string
      dueDate: string | null
      suggestedAssignee: string | null
    },
  ) =>
    apiPatch<Suggestion>(`/clubs/${id(clubId)}/task-suggestions/${id(suggestion.id)}`, {
      expectedVersion: suggestion.version,
      ...values,
    }),
}
