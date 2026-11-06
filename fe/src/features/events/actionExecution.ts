// 승인이 끝나 운영진이 밖에서 직접 할 차례인 일(실행 대기)의 안내와 버튼 이름.
// Step 모달의 Action 카드와 L2 지금 할 일이 같이 쓴다.
import type { ActionType } from '@/features/events/types'
import { copyText } from '@/shared/lib/clipboard'
import { toast } from '@/shared/lib/toast'

export type DoableType = Exclude<ActionType, 'CONFIRMATION'>

// 실행 대기: 승인은 끝났고 운영진이 밖에서 직접 할 차례. copy면 왼쪽 버튼이 박스 내용을 복사한다.
export const APPROVED_STEP: Record<
  DoableType,
  { hint: string; secondary: string; copy: boolean; primary: string }
> = {
  NOTICE: {
    hint: '단톡방에 복사해 붙여넣은 뒤 눌러 주세요',
    secondary: '문구 복사',
    copy: true,
    primary: '게시했습니다',
  },
  EXTERNAL_SEND: {
    hint: '문자로 직접 보낸 뒤 눌러 주세요',
    secondary: '문구 복사',
    copy: true,
    primary: '발송했습니다',
  },
  CONTRACT: {
    hint: '업체와 직접 계약한 뒤 계약서를 등록해 주세요',
    secondary: '조건 보기',
    copy: false,
    primary: '계약서 등록',
  },
  TRANSFER: {
    hint: '은행 앱에서 직접 이체한 뒤 눌러 주세요',
    secondary: '계좌 복사',
    copy: true,
    primary: '이체했습니다',
  },
  EXPENSE: {
    hint: '장부에 반영되면 눌러 주세요',
    secondary: '항목 보기',
    copy: false,
    primary: '장부 반영',
  },
}

export async function copy(text: string) {
  const ok = await copyText(text)
  toast.show(
    ok
      ? { kind: 'done', title: '복사했어요', desc: text }
      : { kind: 'error', title: '복사하지 못했어요', desc: '직접 골라서 복사해 주세요.' },
  )
}
