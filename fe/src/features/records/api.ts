// 서버 호출 함수 + 응답 타입 — FE API 명세 §4 동아리 기록.
//
// BE의 `app/routers/records.py`가 아직 비어 있어서 **이 호출들은 지금 아무도 부르지
// 않는다.** 화면은 훅에서 목업으로만 움직인다(M1·L2와 같은 방식).
// 엔드포인트가 생기는 것부터 hooks.ts의 해당 함수를 여기 호출로 갈아끼우면 된다.
import {
  apiDelete,
  apiDownload,
  apiGet,
  apiGetPage,
  apiPatch,
  apiPost,
  apiPostForm,
} from '@/shared/api/client'
import type {
  ChatAnswer,
  ChatRequestMessage,
  RecordCategory,
  RecordDetail,
  RecordFileType,
  RecordListItem,
  RecordListMeta,
  RecordParseStatus,
} from '@/features/records/types'

// TODO: 로그인 응답의 소속 동아리로 바꾼다. 아직 클럽 컨텍스트가 없어 명세 예시값을 쓴다.
export const CURRENT_CLUB_ID = 'clb_3a71c0'

export interface RecordListResult {
  records: RecordListItem[]
  meta: RecordListMeta
}

// meta는 명세상 항상 채워져 오지만 봉투 타입이 nullable이라, 없으면 목록에서 직접 센다.
function countFrom(records: RecordListItem[]): RecordListMeta {
  const categoryCounts: RecordListMeta['categoryCounts'] = {}
  for (const record of records) {
    categoryCounts[record.category] = (categoryCounts[record.category] ?? 0) + 1
  }
  return {
    totalCount: records.length,
    categoryCounts,
    indexedCount: records.filter((record) => record.parseStatus === 'INDEXED').length,
  }
}

// GET /records — 페이지네이션 없이 전체를 받는다(명세: 4개 카테고리를 한 화면에 펼침).
export async function getRecords(clubId: string = CURRENT_CLUB_ID): Promise<RecordListResult> {
  const body = await apiGetPage<RecordListItem, RecordListMeta>(
    `/records?clubId=${encodeURIComponent(clubId)}`,
  )
  return { records: body.data, meta: body.meta ?? countFrom(body.data) }
}

// GET /records/{recordId} — parseError는 단건에만 있다. "왜 못 읽었나" 박스의 원천.
export function getRecordDetail(recordId: string): Promise<RecordDetail> {
  return apiGet<RecordDetail>(`/records/${recordId}`)
}

// POST /records — multipart. category를 생략하면 AI가 분류하고 ETC로 기본 처리한다.
export function uploadRecord(
  file: File,
  category?: RecordCategory,
  eventId?: string,
  clubId: string = CURRENT_CLUB_ID,
): Promise<RecordListItem> {
  const form = new FormData()
  form.append('file', file)
  form.append('clubId', clubId)
  if (category) form.append('category', category)
  if (eventId) form.append('eventId', eventId)
  return apiPostForm<RecordListItem>('/records', form)
}

// PATCH /records/{recordId} — 카테고리를 바꾸면 파서가 달라져 parseStatus가 PARSING으로 돌아간다.
export function changeRecordCategory(
  recordId: string,
  category: RecordCategory,
): Promise<Pick<RecordListItem, 'id' | 'category' | 'parseStatus'>> {
  return apiPatch(`/records/${recordId}`, { category })
}

// DELETE /records/{recordId} — 204, 본문 없음.
export function deleteRecord(recordId: string): Promise<void> {
  return apiDelete<void>(`/records/${recordId}`)
}

// POST /records/{recordId}/column-mapping — { 표준 열 이름: 파일의 실제 열 이름 }.
// 입금·출금이 한 열에 섞인 경우가 흔해 같은 값이 두 번 들어올 수 있다.
export function submitColumnMapping(
  recordId: string,
  mapping: Record<string, string>,
): Promise<Pick<RecordListItem, 'id' | 'parseStatus'>> {
  return apiPost(`/records/${recordId}/column-mapping`, { mapping })
}

// GET /records/template — text/csv 스트림. 현재 양식은 LEDGER만 있다.
export function downloadLedgerTemplate(): Promise<void> {
  return apiDownload('/records/template?category=LEDGER', '장부 양식.csv')
}

// POST /records/chat — 세션을 저장하지 않으므로 이전 대화 전체를 매 요청에 실어 보낸다.
export function askRecords(
  messages: ChatRequestMessage[],
  clubId: string = CURRENT_CLUB_ID,
): Promise<ChatAnswer> {
  return apiPost<ChatAnswer>('/records/chat', { clubId, messages })
}

// ── 목업 ──
// API가 아직 안 떠 있을 때 화면을 확인하기 위한 것. 시안과 같은 데이터다.
// 카드 머리의 "8건"은 meta.categoryCounts에서 오고 줄 수와 다르다(시안도 그렇다).

// 시안의 .docx·.md는 RecordFileType에 담을 값이 없어(업로드도 막힌다) 허용 형식으로 바꿨다.
const MOCK_SEEDS: Array<
  [
    fileName: string,
    fileType: RecordFileType,
    category: RecordCategory,
    status: RecordParseStatus,
    createdAt: string,
  ]
> = [
  ['동아리 회칙 (2024 개정).pdf', 'PDF', 'PLAN', 'INDEXED', '2026-03-01T02:00:00Z'],
  ['회비 및 환불 규정.hwp', 'HWP', 'PLAN', 'INDEXED', '2026-03-01T02:00:00Z'],
  ['임원 선출 규정.hwp', 'HWP', 'PLAN', 'INDEXED', '2026-02-28T05:00:00Z'],
  ['2025 봄 MT 결과보고.hwp', 'HWP', 'NOTICE', 'INDEXED', '2026-02-28T05:00:00Z'],
  ['2025 신환회 정리.hwp', 'HWP', 'NOTICE', 'INDEXED', '2026-02-28T05:00:00Z'],
  ['2025 여름 해커톤 회고.pdf', 'PDF', 'NOTICE', 'PARSING', '2026-02-28T05:00:00Z'],
  ['2025 하반기 장부.xlsx', 'XLSX', 'LEDGER', 'INDEXED', '2026-02-28T05:00:00Z'],
  ['2025 상반기 장부.xlsx', 'XLSX', 'LEDGER', 'INDEXED', '2026-02-28T05:00:00Z'],
  ['2024 하반기 장부.csv', 'CSV', 'LEDGER', 'NEEDS_REVIEW', '2026-02-28T05:00:00Z'],
  ['단톡방 공지 캡처.png', 'IMAGE', 'ETC', 'FAILED', '2026-03-02T01:00:00Z'],
  ['미분류 문서.pdf', 'PDF', 'ETC', 'FAILED', '2026-03-02T01:00:00Z'],
]

export function getRecordsMock(): RecordListResult {
  return {
    records: MOCK_SEEDS.map(([fileName, fileType, category, parseStatus, createdAt], index) => ({
      id: `rec_${String(index + 1).padStart(2, '0')}`,
      fileName,
      fileType,
      category,
      size: 20114 + index * 3011,
      parseStatus,
      createdAt,
    })),
    meta: {
      totalCount: 25,
      categoryCounts: { PLAN: 3, NOTICE: 8, LEDGER: 12, ETC: 2 },
      indexedCount: 22,
    },
  }
}

// 파싱이 멈춘 세 건의 단건 응답. 명세 §4 `GET /records/{recordId}` 예시 모양이다.
export function getRecordDetailsMock(): Record<string, RecordDetail> {
  const list = getRecordsMock().records
  const detailOf = (
    item: RecordListItem,
    parseError: RecordDetail['parseError'],
  ): RecordDetail => ({
    id: item.id,
    fileName: item.fileName,
    fileType: item.fileType,
    category: item.category,
    parseStatus: item.parseStatus,
    parseResult: null,
    parseError,
    createdAt: item.createdAt,
  })

  const ledger = list[8]
  const capture = list[9]
  const unclassified = list[10]

  return {
    [ledger.id]: detailOf(ledger, {
      reason: 'COLUMN_MISMATCH',
      params: {
        expectedColumns: ['날짜', '적요', '입금', '출금'],
        actualColumns: ['일자', '내용', '금액', '구분'],
      },
      debugMessage: '열 이름이 표준과 달라 어떤 값이 금액인지 찾지 못했습니다.',
    }),
    [capture.id]: detailOf(capture, {
      reason: 'IMAGE_NOT_READABLE',
      params: null,
      debugMessage: 'OCR을 돌리지 않아 이미지에서 글자를 뽑지 못했습니다.',
    }),
    [unclassified.id]: detailOf(unclassified, {
      reason: 'IMAGE_NOT_READABLE',
      params: null,
      debugMessage: '스캔 PDF라 텍스트 레이어가 없습니다.',
    }),
  }
}

// 명세 §4 `POST /records/chat` 응답 예시. R1-b 패널을 확인하기 위한 목업이다.
export function getChatAnswerMock(): ChatAnswer {
  return {
    content:
      '네. 예비비 130,000원을 잡았는데 실제로는 172,000원을 썼고, 초과분 42,000원은 총무가 먼저 내고 나중에 정산했습니다.',
    sources: [
      {
        recordId: 'rec_07',
        fileName: '2025 하반기 장부.xlsx',
        location: { label: '회비 수납 시트' },
      },
      {
        recordId: 'rec_04',
        fileName: '2025 봄 MT 결과보고.hwp',
        location: { label: '예산 항목' },
      },
    ],
    notFound: '무엇에 초과 지출했는지는 장부에 항목이 비어 있어 확인할 수 없습니다.',
    suggestions: [
      '올해는 예비비를 얼마로 잡는 게 좋을까?',
      '작년 MT 참가 취소는 몇 건이었어?',
      '환불 기준이 회칙에 있어?',
    ],
  }
}
