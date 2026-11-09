import { ApiError } from '@/shared/api/types'
import type { ClubRecord, RecordCategory, RecordParseStatus } from '@/features/records/types'

export const RECORD_CATEGORIES: Array<{ value: RecordCategory; label: string }> = [
  { value: 'RULES', label: '회칙 · 규칙' },
  { value: 'EVENT_HISTORY', label: '과거 행사 기록' },
  { value: 'LEDGER', label: '입출금 장부' },
  { value: 'RECEIPT', label: '영수 내역' },
  { value: 'ETC', label: '기타' },
]

interface RecordStatusView {
  label: string
  description: string
  tone: 'neutral' | 'done' | 'approved' | 'pending' | 'failed'
}

export const RECORD_STATUS: Record<RecordParseStatus, RecordStatusView> = {
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

// 회계에서 지출로 확정한 영수증 사진. 자료함 파서는 PDF·CSV·XLSX만 읽어 이미지는 색인하지 않는다.
// 사용처·금액은 이미 장부 지출로 남아 있어 검색에 보탤 것도 없다. 그래서 COMPLETED에서 멈춰 있는데,
// 그대로 보이면 '검색 준비 전'을 영원히 기다리는 것처럼 보인다.
export function isExpenseEvidence(record: Pick<ClubRecord, 'fileType'>): boolean {
  return record.fileType === 'IMAGE'
}

const EXPENSE_EVIDENCE_STATUS: RecordStatusView = {
  label: '지출 증빙',
  description: '장부에 지출로 저장한 영수증 사진이에요. 자료 검색에는 쓰지 않아요.',
  tone: 'neutral',
}

export function recordStatus(
  record: Pick<ClubRecord, 'fileType' | 'parseStatus'>,
): RecordStatusView {
  return isExpenseEvidence(record) ? EXPENSE_EVIDENCE_STATUS : RECORD_STATUS[record.parseStatus]
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

// --- 자료함 검색 결과 목록 ---------------------------------------------------------------
// 순서는 서버가 정한다(record_discovery_service): 제목(파일명) 일치 → 본문 일치 → AI 추천만,
// 같은 묶음 안에서는 AI 관련도가 높은 순. 여기서는 순서를 바꾸지 않고
// 분류로 좁히기 · 검색어 강조 · 나온 이유 표시만 정한다.
type MatchType = 'FILENAME' | 'CONTENT' | 'SEMANTIC'

const MATCH_LABEL: Record<MatchType, string> = {
  FILENAME: '제목 일치',
  CONTENT: '본문 일치',
  SEMANTIC: 'AI 추천',
}

export function matchLabel(types: readonly MatchType[]): string {
  return types.map((type) => MATCH_LABEL[type]).join(' · ')
}

export function filterByCategory<T extends { category: RecordCategory }>(
  items: T[],
  category: RecordCategory | null,
): T[] {
  return category ? items.filter((item) => item.category === category) : items
}

// 결과의 분류가 둘 이상일 때만 칩을 보여 준다. 첫 칩은 전체다.
export function categoryChips(items: Array<{ category: RecordCategory }>) {
  const chips = RECORD_CATEGORIES.map((entry) => ({
    value: entry.value as RecordCategory | null,
    label: entry.label,
    count: items.filter((item) => item.category === entry.value).length,
  })).filter((chip) => chip.count > 0)
  if (chips.length < 2) return []
  return [{ value: null, label: '전체', count: items.length }, ...chips]
}

// 발췌 안의 검색어 위치를 나눈다(대소문자 무시). hit인 조각을 강조한다.
export function highlightParts(text: string, query: string): Array<{ text: string; hit: boolean }> {
  if (!query) return [{ text, hit: false }]
  const parts: Array<{ text: string; hit: boolean }> = []
  const lower = text.toLocaleLowerCase()
  const needle = query.toLocaleLowerCase()
  let from = 0
  for (let at = lower.indexOf(needle); at >= 0; at = lower.indexOf(needle, from)) {
    if (at > from) parts.push({ text: text.slice(from, at), hit: false })
    parts.push({ text: text.slice(at, at + query.length), hit: true })
    from = at + query.length
  }
  if (from < text.length || !parts.length) parts.push({ text: text.slice(from), hit: false })
  return parts
}
