import { useMutation } from '@tanstack/react-query'
import { acceptInvitation, createClub } from '@/features/clubs/api'
import { ApiError } from '@/shared/api/types'

export function useCreateClub() {
  return useMutation({ mutationFn: createClub })
}

export function useJoinClub() {
  return useMutation({ mutationFn: acceptInvitation })
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
