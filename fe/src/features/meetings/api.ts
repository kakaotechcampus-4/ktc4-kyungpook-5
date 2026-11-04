import { apiGet, apiGetPage, apiPatch, apiPost } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import type { Decision, Job, Meeting, MeetingReview, Suggestion, TranscriptList } from './types'
const id = encodeURIComponent
type PageMeta = components['schemas']['PageMeta']
export const meetingsApi = {
  create: (clubId: string, title: string) =>
    apiPost<Meeting>(`/clubs/${id(clubId)}/meetings`, {
      title,
      language: 'ko-KR',
      recordingConsentConfirmed: true,
    }),
  get: (meetingId: string) => apiGet<Meeting>(`/meetings/${id(meetingId)}`),
  list: (clubId: string, status?: Meeting['status']) => {
    const params = new URLSearchParams({ size: '100' })
    if (status) params.set('status', status)
    return apiGetPage<Meeting, PageMeta>(
      `/clubs/${id(clubId)}/meetings?${params.toString()}`,
    )
  },
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
  review: (meetingId: string) => apiPost<MeetingReview>(`/meetings/${id(meetingId)}/review`),
  getReview: (meetingId: string) => apiGet<MeetingReview>(`/meetings/${id(meetingId)}/review`),
  submitReview: (meetingId: string) => apiPost<MeetingReview>(`/meetings/${id(meetingId)}/review/submit`),
  pollReview: (meetingId: string) => apiPost<MeetingReview>(`/meetings/${id(meetingId)}/review/poll`),
  updateReviewSpeakers: (meetingId: string, expectedVersion: number, names: Record<string, string>) =>
    apiPatch<MeetingReview>(`/meetings/${id(meetingId)}/review/speakers`, { expectedVersion, names }),
  createReviewDraft: (meetingId: string, expectedVersion: number) =>
    apiPost<MeetingReview>(`/meetings/${id(meetingId)}/review/draft`, { expectedVersion }),
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
