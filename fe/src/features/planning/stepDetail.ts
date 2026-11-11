// 세부 수정 모달이 어떤 밭을 그릴지(#106). 단계에 붙은 Action 의 type 이 정한다.
// 서버가 ActionOut.payload 를 내려주기 시작해서, 전처럼 단계별 표를 들고 있지 않는다.
import type { components } from '@/shared/api/schema'

type S = components['schemas']
export type StepAction = S['PlannedStepActionOut']
export type ActionPayload = S['ActionPayloadOut']

export type PayloadField = keyof ActionPayload

export interface FieldSpec {
  key: PayloadField
  label: string
  kind: 'text' | 'check' | 'choice'
  hint?: string
}

const FIELDS: Record<PayloadField, Omit<FieldSpec, 'key'>> = {
  channel: { label: '올릴 곳', kind: 'text', hint: '예: 단톡방' },
  audience: { label: '대상', kind: 'text', hint: '예: 전체 회원' },
  sendTiming: { label: '안내 시점', kind: 'text', hint: '예: D-2' },
  vendor: { label: '업체', kind: 'text' },
  cancelTerms: { label: '취소 조건', kind: 'text', hint: '환불 판단에 씁니다' },
  account: { label: '받는 계좌', kind: 'text' },
  receiptRequired: { label: '영수증 필수', kind: 'check' },
  approvalMode: { label: '승인 방식', kind: 'choice' },
}

const BY_TYPE: Record<string, PayloadField[]> = {
  NOTICE: ['channel', 'audience'],
  EXTERNAL_SEND: ['channel', 'audience', 'sendTiming'],
  CONTRACT: ['vendor', 'cancelTerms'],
  TRANSFER: ['account'],
  EXPENSE: ['receiptRequired', 'approvalMode'],
  // CONFIRMATION 의 payload 는 선택지라 세부 수정 대상이 아니다. 서버도 비워 보낸다.
  CONFIRMATION: [],
}

export function fieldsForAction(action: StepAction): FieldSpec[] {
  return (BY_TYPE[action.type] ?? []).map((key) => ({ key, ...FIELDS[key] }))
}

// 금액은 단계마다 뜻이 다르다. #106 의 표에 적힌 이름을 그대로 쓴다.
const AMOUNT_LABEL: Record<string, string> = {
  BOOK_VENUE: '계약금',
  COLLECT_FEES: '1인 금액',
  SETTLE_EXPENSES: '예산 한도',
  REFUND_FEES: '금액',
}

export const amountLabel = (stepCode: string) => AMOUNT_LABEL[stepCode] ?? '금액'

// 참가비 수금의 1인 금액과 지출 정산의 예산 한도는 Event 로 파생된다(#106 ②).
export const DERIVES_TO_EVENT: Record<string, string> = {
  COLLECT_FEES: '행사의 1인 참가비가 이 값을 따릅니다',
  SETTLE_EXPENSES: '행사의 총예산이 이 값을 따릅니다',
}

// 서버는 송금 행동을 실행 완료할 때 이 금액을 그대로 장부 지출로 남긴다(#348).
// 환급은 1인 금액으로 오해하기 쉬워 총액임을 밝힌다(#367).
const AMOUNT_HINT: Record<string, string> = {
  REFUND_FEES: '총 환급액(원) · 실행을 마치면 이 금액이 장부 지출로 남아요',
}

export const amountHint = (stepCode: string) =>
  DERIVES_TO_EVENT[stepCode] ?? AMOUNT_HINT[stepCode] ?? '원'

// 금액이 없는 유형에는 금액 칸을 그리지 않는다. 서버가 null 로 둔 채 쓰지 않는다.
// 송금은 비어 있어도 연다 — 계획이 만든 송금은 금액이 늘 비어 있고, 넣어야 지출로 남는다(#367).
export function showsAmount(action: StepAction, stepCode: string): boolean {
  return action.type === 'TRANSFER' || action.amount !== null || stepCode in DERIVES_TO_EVENT
}
