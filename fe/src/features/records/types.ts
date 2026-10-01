// 도메인 타입 정의 — FE API 명세 §4 `동아리 기록 (R1)` 응답 모양을 그대로 따른다.
export type RecordCategory = 'LEDGER' | 'PLAN' | 'NOTICE' | 'ETC'

export type RecordParseStatus = 'PARSING' | 'NEEDS_REVIEW' | 'COMPLETED' | 'INDEXED' | 'FAILED'

// BE `core/enums.py`의 RecordFileType과 정확히 같다. 서버가 이 다섯 가지 말고는
// 담을 자리가 없으므로, 그 밖의 형식은 올리기 전에 막는다(labels.ts rejectUploadReason).
export type RecordFileType = 'XLSX' | 'CSV' | 'HWP' | 'PDF' | 'IMAGE'

// GET /records — data[]
export interface RecordListItem {
  id: string
  fileName: string
  fileType: RecordFileType
  category: RecordCategory
  size: number
  parseStatus: RecordParseStatus
  createdAt: string
}

// GET /records — meta. 페이지네이션이 없어 page/size는 내려오지 않는다.
export interface RecordListMeta {
  totalCount: number
  categoryCounts: Partial<Record<RecordCategory, number>>
  indexedCount: number
}

// 명세: 값 목록은 파서 구현 시 확정되며 이후로도 추가만 된다.
// **모르는 reason은 FE가 UNKNOWN으로 취급한다** (normalizeParseErrorReason).
export type ParseErrorReason =
  'COLUMN_MISMATCH' | 'IMAGE_NOT_READABLE' | 'UNSUPPORTED_FORMAT' | 'UNKNOWN'

export interface ParseErrorParams {
  expectedColumns?: string[]
  actualColumns?: string[]
}

export interface ParseError {
  reason: ParseErrorReason
  params: ParseErrorParams | null
  // 로그용 원문. 명세상 **화면에 노출하지 않는다** — 문구는 reason으로 FE가 만든다.
  debugMessage: string
}

// GET /records/{recordId} — 단건. size는 응답 예시에 없어 빼둔다.
export interface RecordDetail extends Omit<RecordListItem, 'size'> {
  parseResult: unknown
  parseError: ParseError | null
}

// ── POST /records/chat ──
export type MessageRole = 'USER' | 'ASSISTANT' | 'SYSTEM'

export interface ChatSource {
  recordId: string
  fileName: string
  // v1에서 문자열 → 객체로 바뀌었다. 나중에 sheet·row·page가 늘어도 안 깨지게 객체로 받는다.
  location: { label: string }
}

export interface ChatRequestMessage {
  role: MessageRole
  content: string
}

export interface ChatAnswer {
  content: string
  sources: ChatSource[]
  notFound: string | null
  suggestions: string[]
}

// 화면에는 답변과 그 답변의 근거를 한 덩어리로 그려야 해서 서버로 보내는 모양과 따로 둔다.
export interface ChatTurn extends ChatRequestMessage {
  sources?: ChatSource[]
  notFound?: string | null
}
