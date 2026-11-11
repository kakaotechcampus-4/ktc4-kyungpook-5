import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  acceptInvitation,
  createClub,
  createInvitation,
  getClub,
  listClubMembers,
  updateClub,
} from '@/features/clubs/api'
import type { ClubUpdateInput } from '@/features/clubs/types'
import { ApiError } from '@/shared/api/types'

export function useCreateClub() {
  return useMutation({ mutationFn: createClub })
}

export function useJoinClub() {
  return useMutation({ mutationFn: acceptInvitation })
}

export function useClub(clubId: string | null) {
  return useQuery({
    queryKey: ['clubs', clubId, 'detail'],
    queryFn: () => getClub(clubId as string),
    enabled: Boolean(clubId),
    staleTime: 30_000,
  })
}

// 이름이 바뀌면 /me 의 소속 이름과 상단 드롭다운도 달라진다. 둘 다 다시 받는다.
export function useUpdateClub(clubId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ClubUpdateInput) => updateClub(clubId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['clubs', clubId] })
      void queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
    },
  })
}

export function useClubMembers(clubId: string | null, enabled = true) {
  return useQuery({
    queryKey: ['clubs', clubId, 'members'],
    queryFn: () => listClubMembers(clubId as string),
    enabled: Boolean(clubId) && enabled,
    staleTime: 30_000,
  })
}

export function useCreateInvitation() {
  return useMutation({
    mutationFn: ({ clubId, email, role }: { clubId: string; email: string; role: 'OWNER' | 'MANAGER' }) =>
      createInvitation(clubId, { email, role }),
  })
}

// 초대·생성 실패는 서버가 fields에 "이미 처리된 초대입니다" 같은 이유를 적어 보낸다.
// 그 문구가 코드로 뭉뚱그린 문장보다 정확해서 있으면 그대로 쓴다.
export function clubErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const reason = error.fields && Object.values(error.fields)[0]
    if (reason) return reason
    if (error.code === 'UNAUTHORIZED') return '로그인이 만료됐어요. 다시 로그인해 주세요.'
    if (error.code === 'FORBIDDEN') return '이 작업을 할 권한이 없어요.'
    return '요청을 처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  }
  return '서버에 연결하지 못했어요. 연결 상태를 확인해 주세요.'
}
