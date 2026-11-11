import { apiGet, apiGetBlob, apiGetPage, apiPatch, apiPost } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import type { Decision, Job, Meeting, MeetingReview, Suggestion, TranscriptList } from './types'
const id = encodeURIComponent
type PageMeta = components['schemas']['PageMeta']
type SuggestionFields = {
  title: string
  description: string
  dueDate: string | null
  suggestedAssignee: string | null
}
// 서버는 AI 초안(draft)을 snake_case 그대로 내려보낸다(MeetingReviewOut.draft는 dict).
// 화면은 camelCase로 읽으므로 여기서 맞춘다. 맞추지 않으면 패널이 undefined.length로 죽는다.
type RawDraftItem = Record<string, unknown>
const textOrNull = (value: unknown) => (typeof value === 'string' ? value : null)
const segmentIds = (item: RawDraftItem) => {
  const value = item.evidenceSegmentIds ?? item.evidence_segment_ids
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}
function normalizeReview(review: MeetingReview): MeetingReview {
  const draft = review.draft as { summary?: RawDraftItem[]; tasks?: RawDraftItem[] } | null
  if (!draft) return review
  return {
    ...review,
    draft: {
      summary: (draft.summary ?? []).map((item) => ({
        text: textOrNull(item.text) ?? '',
        evidenceSegmentIds: segmentIds(item),
      })),
      tasks: (draft.tasks ?? []).map((item) => ({
        title: textOrNull(item.title) ?? '',
        description: textOrNull(item.description),
        suggestedAssignee: textOrNull(item.suggestedAssignee ?? item.suggested_assignee),
        suggestedAssigneeMemberId: textOrNull(
          item.suggestedAssigneeMemberId ?? item.suggested_assignee_member_id,
        ),
        dueDate: textOrNull(item.dueDate ?? item.due_date),
        evidenceSegmentIds: segmentIds(item),
      })),
    },
  }
}
export const meetingsApi = {
  // Pressing start is the recording consent (#113); there is no separate checkbox.
  create: (clubId: string, title: string, eventId: string | null) =>
    apiPost<Meeting>(`/clubs/${id(clubId)}/meetings`, {
      title,
      language: 'ko-KR',
      recordingConsentConfirmed: true,
      eventId,
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
  review: (meetingId: string) => apiPost<MeetingReview>(`/meetings/${id(meetingId)}/review`).then(normalizeReview),
  getReview: (meetingId: string) => apiGet<MeetingReview>(`/meetings/${id(meetingId)}/review`).then(normalizeReview),
  submitReview: (meetingId: string) => apiPost<MeetingReview>(`/meetings/${id(meetingId)}/review/submit`).then(normalizeReview),
  pollReview: (meetingId: string) => apiPost<MeetingReview>(`/meetings/${id(meetingId)}/review/poll`).then(normalizeReview),
  updateReviewSpeakers: (meetingId: string, expectedVersion: number, names: Record<string, string>, members: Record<string, { memberId: string | null; confirmed: boolean }>) =>
    apiPatch<MeetingReview>(`/meetings/${id(meetingId)}/review/speakers`, { expectedVersion, names, members }).then(normalizeReview),
  saveReviewCandidates: (meetingId: string, expectedVersion: number, clientRequestId: string, candidates: Array<{ title: string; description: string | null; assigneeMemberId: string | null; dueDate: string | null; evidenceSegmentIds: string[] }>) =>
    apiPost<components['schemas']['TaskSuggestionOut'][]>(`/meetings/${id(meetingId)}/review/candidates`, { expectedVersion, clientRequestId, candidates }),
  reviewSegmentClip: (meetingId: string, segmentId: string) => apiGetBlob(`/meetings/${id(meetingId)}/review/segments/${id(segmentId)}/clip`),
  createReviewDraft: (meetingId: string, expectedVersion: number) =>
    apiPost<MeetingReview>(`/meetings/${id(meetingId)}/review/draft`, { expectedVersion }).then(normalizeReview),
  patchSuggestion: (
    clubId: string,
    suggestion: Suggestion,
    values: SuggestionFields,
  ) =>
    apiPatch<Suggestion>(`/clubs/${id(clubId)}/task-suggestions/${id(suggestion.id)}`, {
      expectedVersion: suggestion.version,
      ...values,
    }),
  acceptSuggestion: async (
    clubId: string,
    suggestion: Suggestion,
    values: SuggestionFields,
  ): Promise<Suggestion> => {
    const saved = await meetingsApi.patchSuggestion(clubId, suggestion, values)
    return apiPost<Suggestion>(`/clubs/${id(clubId)}/task-suggestions/${id(saved.id)}/accept`, {
      expectedVersion: saved.version,
    })
  },
}
