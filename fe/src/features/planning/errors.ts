import { ApiError } from '@/shared/api/types'

export class PartialPlanSaveError extends Error {
  constructor(
    public readonly completed: string[],
    public readonly failedCount: number,
  ) {
    super(
      `${completed.join(' · ')}은 저장됐어요. 저장하지 못한 항목 ${failedCount}건이 있어 최신 계획을 다시 불러온 뒤 다시 시도해 주세요.`,
    )
    this.name = 'PartialPlanSaveError'
  }
}

export function planningError(error: unknown): string {
  if (error instanceof PartialPlanSaveError) return error.message
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      VERSION_CONFLICT: '다른 변경이 있어요. 최신 계획을 다시 불러온 뒤 다시 시도해 주세요.',
      PLANNING_STATE_CONFLICT:
        '저장된 계획 상태가 바뀌었어요. 최신 계획을 다시 불러온 뒤 다시 시도해 주세요.',
      NOT_EDITABLE: '이미 끝난 단계나 작업은 수정할 수 없어요.',
      FORBIDDEN: '이 계획을 수정할 권한이 없어요.',
      STEP_NOT_FOUND: '단계를 찾지 못했어요. 최신 계획을 다시 불러와 주세요.',
      ACTION_NOT_FOUND: '작업을 찾지 못했어요. 최신 계획을 다시 불러와 주세요.',
      VALIDATION_FAILED: '입력한 내용을 확인해 주세요.',
    }
    return messages[error.code] ?? '계획을 저장하지 못했어요. 최신 계획을 다시 불러와 주세요.'
  }
  return '계획 저장 결과를 확인하지 못했어요. 최신 계획을 다시 불러온 뒤 다시 시도해 주세요.'
}
