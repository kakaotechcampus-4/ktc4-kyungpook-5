// 세부 수정 모달이 단계마다 어떤 밭을 그릴지(#106).
// 단계에 붙은 Action 유형이 밭을 정한다. 13개 중 8개는 일정 말고 고칠 게 없다 —
// 확인 요청만 붙었거나(4개) Action 이 아예 없어서(행사 당일)다.
//
// 서버가 ActionOut 을 내려주기 시작하면 이 표 대신 응답의 type·payload 를 보고
// 그리면 된다. 지금은 Action 레코드가 FE 로 오지 않아 카탈로그로 대신한다.

export type DetailField =
  | 'title'
  | 'dueDate'
  | 'amount'
  | 'channel'
  | 'audience'
  | 'sendTiming'
  | 'vendor'
  | 'cancelTerms'
  | 'account'
  | 'receiptRequired'
  | 'approvalMode'

export interface FieldSpec {
  key: DetailField
  label: string
  kind: 'text' | 'date' | 'money' | 'check' | 'choice'
  hint?: string
}

const FIELDS: Record<DetailField, Omit<FieldSpec, 'key'>> = {
  title: { label: '제목', kind: 'text' },
  dueDate: { label: '기한', kind: 'date' },
  amount: { label: '금액', kind: 'money' },
  channel: { label: '올릴 곳', kind: 'text', hint: '예: 단톡방' },
  audience: { label: '대상', kind: 'text', hint: '예: 전체 회원' },
  sendTiming: { label: '안내 시점', kind: 'text', hint: '예: D-2' },
  vendor: { label: '업체', kind: 'text' },
  cancelTerms: { label: '취소 조건', kind: 'text', hint: '환불 판단에 씁니다' },
  account: { label: '받는 계좌', kind: 'text' },
  receiptRequired: { label: '영수증 필수', kind: 'check' },
  approvalMode: { label: '승인 방식', kind: 'choice' },
}

// 금액은 단계마다 뜻이 다르다. 표의 이름을 그대로 쓴다.
const AMOUNT_LABEL: Record<string, string> = {
  BOOK_VENUE: '계약금',
  COLLECT_FEES: '1인 금액',
  SETTLE_EXPENSES: '예산 한도',
  REFUND_FEES: '금액',
}

const BY_STEP: Record<string, DetailField[]> = {
  DEMAND_SURVEY: ['title', 'dueDate', 'channel', 'audience'],
  RECRUIT_NOTICE: ['title', 'dueDate', 'channel', 'audience'],
  CHECK_RESPONSES: ['title', 'dueDate', 'channel', 'audience'],
  PRE_EVENT_NOTICE: ['title', 'dueDate', 'channel', 'audience'],
  BOOK_VENUE: ['title', 'dueDate', 'amount', 'vendor', 'cancelTerms', 'account'],
  COLLECT_FEES: ['title', 'dueDate', 'amount', 'channel', 'audience', 'sendTiming'],
  SETTLE_EXPENSES: ['title', 'dueDate', 'amount', 'receiptRequired', 'approvalMode'],
  REFUND_FEES: ['title', 'dueDate', 'amount', 'account'],
}

export function fieldsForStep(code: string): FieldSpec[] {
  return (BY_STEP[code] ?? []).map((key) => ({
    key,
    ...FIELDS[key],
    label: key === 'amount' ? (AMOUNT_LABEL[code] ?? FIELDS.amount.label) : FIELDS[key].label,
  }))
}

// 참가비 수금의 1인 금액과 지출 정산의 예산 한도는 Event 쪽으로 파생된다(#106 ②).
// 고치면 행사 전체 값이 따라 바뀐다는 걸 사용자에게 알려 준다.
export const DERIVES_TO_EVENT: Record<string, string> = {
  COLLECT_FEES: '행사의 1인 참가비가 이 값을 따릅니다',
  SETTLE_EXPENSES: '행사의 총예산이 이 값을 따릅니다',
}
