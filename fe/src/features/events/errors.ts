// 행사 상세에서 쓰는 오류 문구(#375). 회의(meetings/errors.ts)·계획(planning/errors.ts)과 같은 모양이다.
//
// 409는 "잠시 뒤 다시"가 아니다. 서버가 이미 다른 상태라서 막은 것이므로,
// 사용자가 할 일은 재시도가 아니라 바뀐 내용을 보고 다시 정하는 것이다.
// 훅이 onSettled로 목록을 다시 받아 둔 뒤라, 화면은 이미 최신이다.
import { ApiError } from '@/shared/api/types'

const MESSAGES: Record<string, string> = {
  // 보고 있던 사이 누가 먼저 바꿨다. 버전이 어긋나 서버가 막았다.
  VERSION_CONFLICT: '그사이 내용이 바뀌었어요. 화면을 새로 불러왔으니 확인한 뒤 다시 정해 주세요.',
  ALREADY_RESOLVED: '이미 처리된 할 일이에요. 새로 불러온 목록을 확인해 주세요.',
  STEP_ALREADY_COMPLETED: '이미 완료된 단계예요. 새로 불러온 내용을 확인해 주세요.',
  // 행사 완료는 남은 단계·할 일이 없어야 한다.
  EVENT_INCOMPLETE: '남은 단계와 할 일을 먼저 처리해 주세요.',
  EVENT_NOT_ON_GOING: '진행 중인 행사에서만 처리할 수 있어요. 행사를 먼저 시작해 주세요.',
  NOT_EDITABLE: '더 고칠 수 없는 항목이에요.',
  EVENT_NOT_FOUND: '행사를 찾을 수 없어요. 목록에서 다시 골라 주세요.',
  ACTION_NOT_FOUND: '할 일을 찾을 수 없어요. 목록을 다시 확인해 주세요.',
  STEP_NOT_FOUND: '단계를 찾을 수 없어요. 목록을 다시 확인해 주세요.',
  UNAUTHORIZED: '로그인이 만료됐어요. 다시 로그인해 주세요.',
  FORBIDDEN: '이 작업을 할 권한이 없어요.',
}

export function eventError(error: unknown): string {
  if (error instanceof ApiError) {
    // 서버가 fields에 이유를 적어 보내면 그 문구가 더 정확하다(예: 행사 시작에 빠진 값).
    const reason = error.fields && Object.values(error.fields)[0]
    if (reason) return reason
    const known = MESSAGES[error.code]
    if (known) return known
    // 모르는 코드라도 서버 문구는 한국어다. 영문 코드만 덩그러니 보이지 않게 한다.
    return error.message || '요청을 처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  }
  return '서버에 연결하지 못했어요. 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}

// 서버가 "지금 상태에서는 안 된다"고 막은 것들. 다시 눌러도 같은 결과라
// 토스트 제목을 달리해 재시도를 권하지 않는다.
const CONFLICT_CODES = new Set([
  'VERSION_CONFLICT',
  'ALREADY_RESOLVED',
  'STEP_ALREADY_COMPLETED',
  'EVENT_INCOMPLETE',
  'EVENT_NOT_ON_GOING',
  'NOT_EDITABLE',
])

export function isConflict(error: unknown): boolean {
  return error instanceof ApiError && CONFLICT_CODES.has(error.code)
}
