import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type Query,
} from '@tanstack/react-query'
import { useEffect, useMemo, useRef } from 'react'
import { meetingsApi } from './api'
import { sourceOf } from './timeline'
import type { Job, Meeting, Transcript } from './types'
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
  const refresh = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ['meeting', clubId, meetingId] }),
      client.invalidateQueries({ queryKey: ['transcripts', clubId, meetingId] }),
      client.invalidateQueries({ queryKey: ['decisions', clubId, meetingId] }),
      client.invalidateQueries({ queryKey: ['suggestions', clubId, meetingId] }),
    ])
  const finish = useMutation({
    mutationFn: () => meetingsApi.finish(meetingId!),
    onSuccess: refresh,
  })
  return {
    meeting,
    transcripts,
    decisions,
    suggestions: selectedSuggestions,
    suggestionsQuery: suggestions,
    refresh,
    finish,
  }
}
export function useCreateMeeting(clubId: string) {
  return useMutation({ mutationFn: (title: string) => meetingsApi.create(clubId, title) })
}
export function useDecisionJobs(transcripts: Transcript[]) {
  return useQueries({
    queries: transcripts
      .filter((t) => t.final && t.decisionJobId)
      .map((t) => ({
        queryKey: ['decision-job', t.decisionJobId],
        queryFn: () => meetingsApi.job(t.decisionJobId!),
        refetchInterval: (query: Query<Job>) =>
          query.state.data?.status === 'SUCCEEDED' || query.state.data?.status === 'FAILED'
            ? false
            : 3000,
      })),
  })
}
