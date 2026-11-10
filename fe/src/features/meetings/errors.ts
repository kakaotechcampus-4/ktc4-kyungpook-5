import { ApiError } from '@/shared/api/types'

const DIARIZATION_OFF = '화자분리 서비스가 준비되지 않았습니다. 관리자에게 알려 주세요.'
const NOT_FOUND = '항목을 찾을 수 없습니다. 새로고침해 최신 상태를 확인해 주세요.'
const messages: Record<string, string> = {
  UNAUTHORIZED: '로그인 세션이 만료됐습니다. 다시 로그인해 주세요.',
  FORBIDDEN: '서버에서 이 작업의 권한을 허용하지 않았습니다.',
  VALIDATION_FAILED: '입력한 내용을 확인해 주세요.',
  TASK_SUGGESTION_STALE: '근거 전사가 변경됐습니다. 최신 후보를 다시 확인해 주세요.',
  TASK_SUGGESTION_NOT_PROPOSED:
    '이미 확정했거나 정리된 후보입니다. 최신 후보를 다시 확인해 주세요.',
  TASK_SUGGESTION_NOT_FOUND: NOT_FOUND,
  CONFIRMED_TASK_NOT_FOUND: NOT_FOUND,
  REMINDER_DISPATCH_IN_PROGRESS:
    '알림을 발송 중이라 변경할 수 없습니다. 잠시 뒤 상태를 확인해 주세요.',
  CONFIRMED_TASK_CANCELLED: '취소된 항목입니다. 최신 상태를 다시 확인해 주세요.',
  VERSION_CONFLICT: '다른 곳에서 변경됐습니다. 새로고침한 내용을 확인해 주세요.',
  IDEMPOTENCY_CONFLICT:
    '같은 요청이 이미 다른 내용으로 처리됐습니다. 새로고침한 내용을 확인해 주세요.',
  MEETING_NOT_FOUND: '회의를 찾을 수 없습니다. 소속과 회의 주소를 확인해 주세요.',
  MEETING_NOT_RECORDING: '이미 종료됐거나 처리 중인 회의입니다. 상태를 다시 확인해 주세요.',
  AUDIO_STREAM_ACTIVE: '아직 음성을 받는 중인 회의입니다. 녹음 중인 화면에서 회의를 끝내 주세요.',
  MEETING_REVIEW_CONFLICT:
    '지금은 화자 확인을 진행할 수 없습니다. 녹음이 저장된 채 정상 종료된 회의인지 새로고침해 확인해 주세요.',
  // 화자분리 실패. 패널의 「다시 시도」 버튼과 겹치지 않게 무엇이 실패했는지만 적는다.
  DIARIZATION_UNAVAILABLE: DIARIZATION_OFF,
  DIARIZATION_NOT_CONFIGURED: DIARIZATION_OFF,
  DIARIZATION_TIMEOUT: '화자분리 응답 시간이 초과됐습니다.',
  DIARIZATION_PROVIDER_ERROR: '화자분리 서비스 호출에 실패했습니다.',
  DIARIZATION_INVALID_RESPONSE: '화자분리 결과를 읽지 못했습니다.',
  DIARIZATION_UPLOAD_FAILED: '녹음을 화자분리 서비스에 올리지 못했습니다.',
  DIARIZATION_FAILED: '화자분리 서비스가 작업을 끝내지 못했습니다.',
}

export function meetingCodeMessage(code: string): string {
  return messages[code] ?? `요청을 처리하지 못했습니다. (${code})`
}

export function meetingError(error: unknown): string {
  if (error instanceof ApiError) return meetingCodeMessage(error.code)
  // 서버가 오류 봉투 없이 응답한 경우(예: 회의록 초안 AI 실패의 500). 연결 문제가 아니다.
  if ((error as { response?: unknown } | null)?.response)
    return '서버에서 요청을 처리하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'
  return '서버에 연결하지 못했습니다. API 주소와 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}
