// 서버 enum 코드 → 화면 문구. 동아리 기록에서만 쓰므로 shared 대신 여기 둔다.
import type { ParseErrorReason, RecordCategory, RecordFileType } from '@/features/records/types'

// 시안의 카드 순서 그대로다. 기타가 마지막인 건 "되도록 쓰지 마세요" 카드라서다.
export const CATEGORY_ORDER: RecordCategory[] = ['PLAN', 'NOTICE', 'LEDGER', 'ETC']

export const CATEGORY_LABEL: Record<RecordCategory, string> = {
  PLAN: '회칙 · 규칙',
  NOTICE: '과거 행사 기록',
  LEDGER: '입출금 장부',
  ETC: '기타',
}

export const CATEGORY_DESCRIPTION: Record<RecordCategory, string> = {
  PLAN: '회칙과 환불·승인 기준이 담긴 문서. AI가 판단 기준으로 씁니다.',
  NOTICE: '지난 행사의 결과보고와 명단. 계획 1단계에서 불러옵니다.',
  LEDGER: '회비 수납과 지출 내역. 예산 전망의 기준이 됩니다.',
  ETC: '위 세 가지에 속하지 않는 파일. 분류가 없으면 AI가 제대로 활용하지 못합니다.',
}

// 키를 string으로 둔 건 모르는 코드가 와도 화면이 죽지 않게 하려는 것이다(`?? code`로 폴백).
export const PARSE_STATUS_LABEL: Record<string, string> = {
  INDEXED: '읽음',
  PARSING: '읽는 중',
  NEEDS_REVIEW: '형식 확인 필요',
  FAILED: '읽지 못함',
  // 시안에 없는 상태. 파싱은 끝났고 색인(INDEXED) 전이다.
  COMPLETED: '정리됨',
}

// 읽음(INDEXED)만 잔잔한 칩이고, 나머지는 손이 가야 하는 상태라 한 톤 진하게 쓴다.
export function parseStatusChipVariant(status: string): 'subtle' | 'notice' {
  return status === 'INDEXED' || status === 'COMPLETED' ? 'subtle' : 'notice'
}

// 파싱이 멈춘 파일. 이 두 상태일 때만 "왜 못 읽었나" 박스를 그린다.
export function needsParseReason(status: string): boolean {
  return status === 'NEEDS_REVIEW' || status === 'FAILED'
}

// 올릴 수 있는 형식. BE RecordFileType이 다섯 가지뿐이라 그 밖의 파일은 서버가
// 받아도 분류할 코드가 없다. 그래서 확장자를 형식으로 바꿔보고, 안 되면 올리지 않는다.
const FILE_TYPE_BY_EXTENSION: Record<string, RecordFileType> = {
  xlsx: 'XLSX',
  csv: 'CSV',
  hwp: 'HWP',
  pdf: 'PDF',
  png: 'IMAGE',
  jpg: 'IMAGE',
  jpeg: 'IMAGE',
  gif: 'IMAGE',
  webp: 'IMAGE',
}

// <input type="file" accept>에 그대로 넣는다. 파일 선택창이 1차로 걸러 준다.
export const UPLOAD_ACCEPT = Object.keys(FILE_TYPE_BY_EXTENSION)
  .map((extension) => `.${extension}`)
  .join(',')

export function fileTypeOf(fileName: string): RecordFileType | null {
  const extension = fileName.split('.').pop()?.toLowerCase() ?? ''
  return FILE_TYPE_BY_EXTENSION[extension] ?? null
}

// accept는 선택창 필터일 뿐이라 "모든 파일"로 바꾸거나 끌어다 놓으면 뚫린다.
// 보내기 직전에 한 번 더 본다.
export function rejectUploadReason(fileName: string): string | null {
  return fileTypeOf(fileName) ? null : 'xlsx · csv · hwp · pdf · 이미지 파일만 올릴 수 있습니다.'
}

export type ParseErrorAction = 'COLUMN_MAPPING' | 'TEMPLATE' | 'UPLOAD_NEW' | 'DELETE'

// 명세: 서버가 만든 문장(`detail`)을 없앴다. FE가 reason 코드를 보고 문구·버튼을 고른다.
// `debugMessage`는 로그용이라 여기에도, 화면에도 넣지 않는다.
export const PARSE_ERROR_COPY: Record<
  ParseErrorReason,
  { message: string; hint: string | null; actions: ParseErrorAction[] }
> = {
  COLUMN_MISMATCH: {
    message: '열 이름이 표준과 달라 어떤 값이 금액인지 찾지 못했습니다.',
    // 필요한 열 / 이 파일에 있는 열은 params로 만든다(columnHint).
    hint: null,
    actions: ['COLUMN_MAPPING', 'TEMPLATE'],
  },
  IMAGE_NOT_READABLE: {
    message: '이미지 파일이라 글자를 읽을 수 없습니다.',
    hint: '캡처 대신 원본 문서를 올리면 내용을 활용할 수 있습니다.',
    actions: ['UPLOAD_NEW', 'DELETE'],
  },
  UNSUPPORTED_FORMAT: {
    message: '지원하지 않는 파일 형식입니다.',
    hint: null,
    // 명세 예시에는 버튼이 없다. 시안이 IMAGE_NOT_READABLE 박스에 삭제를 둔 것과 맞췄다
    // (⋯ 메뉴에도 있으니 없앨 길이 없는 건 아니고, 박스 안으로 끌어온 지름길이다).
    actions: ['DELETE'],
  },
  UNKNOWN: {
    message: '원인을 확인하지 못했습니다.',
    hint: null,
    actions: [],
  },
}

// 명세: FE는 모르는 reason 값을 받으면 UNKNOWN으로 취급해야 한다.
export function normalizeParseErrorReason(reason: string): ParseErrorReason {
  return reason in PARSE_ERROR_COPY ? (reason as ParseErrorReason) : 'UNKNOWN'
}

// "필요한 열: 날짜 · 적요 · 입금 · 출금  /  이 파일에 있는 열: 일자 · 내용 · 금액 · 구분"
export function columnHint(expected?: string[], actual?: string[]): string | null {
  if (!expected?.length || !actual?.length) return null
  return `필요한 열: ${expected.join(' · ')}  /  이 파일에 있는 열: ${actual.join(' · ')}`
}
