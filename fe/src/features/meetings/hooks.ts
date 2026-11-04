import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { meetingsApi } from './api'
import { sourceOf } from './timeline'
import type { Meeting } from './types'
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
  // Stable so memoised columns do not re-render on every audio level update.
  const refresh = useCallback(
    () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ['meeting', clubId, meetingId] }),
        client.invalidateQueries({ queryKey: ['transcripts', clubId, meetingId] }),
        client.invalidateQueries({ queryKey: ['decisions', clubId, meetingId] }),
        client.invalidateQueries({ queryKey: ['suggestions', clubId, meetingId] }),
      ]),
    [client, clubId, meetingId],
  )
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
