import { ApiError } from '@/shared/api/types'
export function meetingError(error: unknown): string {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      UNAUTHORIZED: '로그인 세션이 만료됐습니다. 다시 로그인해 주세요.',
      FORBIDDEN: '서버에서 이 작업의 권한을 허용하지 않았습니다.',
      TASK_SUGGESTION_STALE: '근거 전사가 변경됐습니다. 최신 후보를 다시 확인해 주세요.',
      REMINDER_DISPATCH_IN_PROGRESS:
        '알림을 발송 중이라 변경할 수 없습니다. 잠시 뒤 상태를 확인해 주세요.',
      CONFIRMED_TASK_CANCELLED: '취소된 항목입니다. 최신 상태를 다시 확인해 주세요.',
      VERSION_CONFLICT: '다른 곳에서 변경됐습니다. 새로고침한 내용을 확인해 주세요.',
      MEETING_NOT_FOUND: '회의를 찾을 수 없습니다. 소속과 회의 주소를 확인해 주세요.',
      MEETING_NOT_RECORDING: '이미 종료됐거나 처리 중인 회의입니다. 상태를 다시 확인해 주세요.',
    }
    return messages[error.code] ?? `요청을 처리하지 못했습니다. (${error.code})`
  }
  return '서버에 연결하지 못했습니다. API 주소와 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}
