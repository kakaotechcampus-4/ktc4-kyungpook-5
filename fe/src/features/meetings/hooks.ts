import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { meetingsApi } from './api'
import { ApiError } from '@/shared/api/types'
import { sourceOf } from './timeline'
import type { Meeting, MeetingReview } from './types'
export function useMeetingData(clubId: string, meetingId: string | undefined) {
  const client = useQueryClient()
  const meeting = useQuery({
    queryKey: ['meeting', clubId, meetingId],
    queryFn: () => meetingsApi.get(meetingId!),
    enabled: !!meetingId,
    refetchInterval: (q) =>
      q.state.data?.status === 'RECORDING' || q.state.data?.status === 'FINALIZING' ? 3000 : false,
  })
  const correctClub = meeting.data?.clubId === clubId
  const interval =
    meeting.data?.status === 'COMPLETED' || meeting.data?.status === 'FAILED' ? false : 2500
  const transcripts = useQuery({
    queryKey: ['transcripts', clubId, meetingId],
    queryFn: () => meetingsApi.transcripts(meetingId!),
    enabled: !!meetingId && correctClub,
    refetchInterval: interval,
  })
  const decisions = useQuery({
    queryKey: ['decisions', clubId, meetingId],
    queryFn: () => meetingsApi.decisions(clubId, meetingId!),
    enabled: !!meetingId && correctClub,
    refetchInterval: interval,
  })
  const suggestions = useQuery({
    queryKey: ['suggestions', clubId, meetingId],
    queryFn: () => meetingsApi.suggestions(clubId),
    enabled: !!meetingId && correctClub,
    refetchInterval: interval,
  })
  const review = useQuery({
    queryKey: ['meeting-review', meetingId],
    queryFn: async () => {
      let review: MeetingReview
      try {
        review = await meetingsApi.getReview(meetingId!)
      } catch (error) {
        // 아직 검토가 없다. undefined를 돌려주면 react-query가 오류로 바꿔 "연결 실패"가 뜬다.
        if (error instanceof ApiError && error.code === 'MEETING_REVIEW_CONFLICT') return null
        throw error
      }
      if (review.status !== 'PROCESSING') return review
      // 서버는 화자분리 결과를 스스로 가져오지 않아 poll로 확인을 요청한다. poll이 실패를
      // 저장했으면(FAILED·errorCode) 그 상태를 보여 주고, 아직 처리 중이면 poll 오류를 알린다.
      return meetingsApi.pollReview(meetingId!).catch(async (error: unknown) => {
        const current = await meetingsApi.getReview(meetingId!)
        if (current.status !== 'PROCESSING') return current
        // 처리 중이라는 사실은 남겨 둬야 4초 확인(refetchInterval)이 이어지고 화면도 실행 전으로 돌아가지 않는다.
        client.setQueryData(['meeting-review', meetingId], current)
        throw error
      })
    },
    enabled: !!meetingId && correctClub && meeting.data?.status === 'COMPLETED',
    retry: false,
    refetchInterval: (q) => q.state.data?.status === 'PROCESSING' || q.state.data?.status === 'SUBMITTING' ? 4000 : false,
  })
  const previousStatus = useRef<{
    meetingId: string | undefined
    status: Meeting['status'] | undefined
  }>({ meetingId, status: undefined })
  useEffect(() => {
    const status = meeting.data?.status
    const previous = previousStatus.current
    previousStatus.current = { meetingId, status }
    // 마지막 전사/AI 저장 뒤 종료 상태가 먼저 도착해도 마지막 결과를 한 번 더 읽는다.
    // 처음부터 종료된 회의를 연 경우에는 각 query의 최초 조회가 이 역할을 한다.
    if (
      !meetingId ||
      previous.meetingId !== meetingId ||
      !previous.status ||
      previous.status === status ||
      (status !== 'COMPLETED' && status !== 'FAILED')
    )
      return
    void Promise.all([
      client.invalidateQueries({ queryKey: ['transcripts', clubId, meetingId] }),
      client.invalidateQueries({ queryKey: ['decisions', clubId, meetingId] }),
      client.invalidateQueries({ queryKey: ['suggestions', clubId, meetingId] }),
      client.invalidateQueries({ queryKey: ['meeting-review', meetingId] }),
    ])
  }, [client, clubId, meetingId, meeting.data?.status])
  const selectedSuggestions = useMemo(
    () =>
      suggestions.data?.filter((s) =>
        decisions.data?.some(
          (d) =>
            d.id === s.decisionId &&
            d.status !== 'STALE' &&
            !!sourceOf(d, transcripts.data?.items ?? []),
        ),
      ) ?? [],
    [suggestions.data, decisions.data, transcripts.data],
  )
  // Stable so memoised columns do not re-render on every audio level update.
  const refresh = useCallback(
    () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ['meeting', clubId, meetingId] }),
        client.invalidateQueries({ queryKey: ['transcripts', clubId, meetingId] }),
        client.invalidateQueries({ queryKey: ['decisions', clubId, meetingId] }),
        client.invalidateQueries({ queryKey: ['suggestions', clubId, meetingId] }),
        client.invalidateQueries({ queryKey: ['meeting-review', meetingId] }),
      ]),
    [client, clubId, meetingId],
  )
  const finish = useMutation({
    mutationFn: () => meetingsApi.finish(meetingId!),
    onSuccess: refresh,
  })
  const startReview = useMutation({ mutationFn: () => meetingsApi.review(meetingId!), onSuccess: refresh })
  const submitReview = useMutation({ mutationFn: () => meetingsApi.submitReview(meetingId!), onSuccess: refresh })
  const updateReviewSpeakers = useMutation({ mutationFn: (input: { version: number; names: Record<string, string>; members: Record<string, { memberId: string | null; confirmed: boolean }> }) => meetingsApi.updateReviewSpeakers(meetingId!, input.version, input.names, input.members), onSuccess: refresh })
  const createReviewDraft = useMutation({ mutationFn: (version: number) => meetingsApi.createReviewDraft(meetingId!, version), onSuccess: refresh })
  const saveReviewCandidates = useMutation({ mutationFn: (input: { version: number; clientRequestId: string; candidates: Array<{ title: string; description: string | null; assigneeMemberId: string | null; dueDate: string | null; evidenceSegmentIds: string[] }> }) => meetingsApi.saveReviewCandidates(meetingId!, input.version, input.clientRequestId, input.candidates), onSuccess: refresh })
  return {
    meeting,
    transcripts,
    decisions,
    suggestions: selectedSuggestions,
    suggestionsQuery: suggestions,
    refresh,
    finish,
    review,
    startReview,
    submitReview,
    updateReviewSpeakers,
    createReviewDraft,
    saveReviewCandidates,
  }
}
export function useMeetings(clubId: string, status?: Meeting['status']) {
  return useQuery({
    queryKey: ['meetings', clubId, status],
    queryFn: () => meetingsApi.list(clubId, status),
    enabled: Boolean(clubId),
    retry: false,
  })
}
export function useCreateMeeting(clubId: string) {
  return useMutation({
    mutationFn: ({ title, eventId }: { title: string; eventId: string | null }) =>
      meetingsApi.create(clubId, title, eventId),
  })
}
