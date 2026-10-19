import { ApiError } from '@/shared/api/types'
import type { RecordCategory, RecordParseStatus } from '@/features/records/types'

export const RECORD_CATEGORIES: Array<{ value: RecordCategory; label: string }> = [
  { value: 'RULES', label: '회칙 · 규칙' },
  { value: 'EVENT_HISTORY', label: '과거 행사 기록' },
  { value: 'LEDGER', label: '입출금 장부' },
  { value: 'RECEIPT', label: '영수 내역' },
  { value: 'ETC', label: '기타' },
]

export const RECORD_STATUS: Record<
  RecordParseStatus,
  { label: string; description: string; tone: 'done' | 'approved' | 'pending' | 'failed' }
> = {
  QUEUED: {
    label: '처리 대기',
    description: '자료를 받았어요. 서버에서 처리할 순서를 기다리고 있어요.',
    tone: 'pending',
  },
  PARSING: {
    label: '내용 읽는 중',
    description: '파일에서 글과 표를 읽고 있어요. 검색 준비는 아직이에요.',
    tone: 'approved',
  },
  NEEDS_REVIEW: {
    label: '형식 확인 필요',
    description: '자료 형식을 확인해야 해요. 검색 준비가 끝나지 않았어요.',
    tone: 'pending',
  },
  COMPLETED: {
    label: '파싱 완료 · 검색 준비 전',
    description: '파일 내용은 읽었어요. 서버의 검색 색인 완료를 기다리고 있어요.',
    tone: 'pending',
  },
  INDEXED: {
    label: '검색 준비 완료',
    description: '이 자료를 회의 중 자료 검색에 사용할 수 있어요.',
    tone: 'done',
  },
  FAILED: {
    label: '처리 실패',
    description: '자료를 처리하지 못했어요. 파일을 확인한 뒤 다시 올려 주세요.',
    tone: 'failed',
  },
}

export function recordErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'UNAUTHORIZED':
        return '로그인 상태를 확인한 뒤 다시 시도해 주세요.'
      case 'FORBIDDEN':
        return '선택한 팀의 자료를 조회하거나 올릴 권한이 없어요.'
      case 'RECORD_NOT_FOUND':
        return '이 자료를 찾을 수 없어요. 자료 ID를 확인해 주세요.'
      case 'VALIDATION_FAILED':
        return '파일과 분류를 확인해 주세요. PDF, CSV, XLSX를 올릴 수 있어요.'
    }
  }
  return '서버에서 자료 처리 결과를 받지 못했어요. 연결을 확인한 뒤 다시 시도해 주세요.'
}

export function parseErrorMessage(error: { [key: string]: unknown } | null): string {
  switch (error?.reason) {
    case 'COLUMN_MISMATCH':
      return '표의 열 구성을 읽지 못했어요. 원본 파일을 확인해 주세요.'
    case 'IMAGE_NOT_READABLE':
      return '읽을 수 있는 글자가 없어요. 스캔 이미지 대신 텍스트가 있는 PDF를 올려 주세요.'
    case 'UNSUPPORTED_FORMAT':
      return '지원하지 않는 형식이거나 파일을 열 수 없어요. 암호 없는 PDF, CSV, XLSX를 확인해 주세요.'
    default:
      return RECORD_STATUS.FAILED.description
  }
}

export function formatFileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
