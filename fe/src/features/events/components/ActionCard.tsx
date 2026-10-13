// Action 카드(Step 모달 안): 유형 · 상태 · 기한 / 제목 · 설명 / 회색 박스 / 버튼.
// 상태(ActionStatus)마다 박스 문구와 버튼이 바뀌고, 실행 대기 버튼은 유형마다 다르다.
// 승인·진행하지 않기는 카드가 아니라 [검토하기]로 여는 결정 검토 모달에서 한다.
import type { ComponentProps, ReactNode } from 'react'
import type { ActionStatus, ActionType, EventAction } from '@/features/events/types'
import { copyText } from '@/shared/lib/clipboard'
import { formatDateTime, formatMonthDay } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL, formatResolver } from '@/shared/lib/labels'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'

const STATUS_CHIP: Record<
  ActionStatus,
  { label: string; tone: ComponentProps<typeof Chip>['tone'] }
> = {
  PENDING: { label: '승인 대기', tone: 'pending' },
  APPROVED: { label: '실행 대기', tone: 'approved' },
  DONE: { label: '완료', tone: 'done' },
  DENIED: { label: '진행 안 함', tone: 'neutral' },
  FAILED: { label: '실패', tone: 'failed' },
}

// 확인 요청은 승인할 일이 아니라 토리의 질문이라 이름만 바꾼다
const QUESTION_CHIP: Partial<Record<ActionStatus, string>> = {
  PENDING: '질문 대기',
  DONE: '답변 완료',
}

type DoableType = Exclude<ActionType, 'CONFIRMATION'>

// 실행 대기: 승인은 끝났고 운영진이 밖에서 직접 할 차례. copy면 왼쪽 버튼이 박스 내용을 복사한다.
const APPROVED_STEP: Record<
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

// 완료 기록의 첫머리
const DONE_LABEL: Record<DoableType, string> = {
  NOTICE: '단톡방에 게시함',
  EXTERNAL_SEND: '발송함',
  CONTRACT: '계약서 등록함',
  TRANSFER: '이체 기록함',
  EXPENSE: '장부에 반영함',
}

// 회색 박스: 작은 제목 · 본문 · 안내 한 줄. 없는 줄은 그리지 않는다.
function Box({ label, children, hint }: { label?: string; children?: ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-[5px] rounded-[11px] bg-bg px-[14px] py-[12px]">
      {label && <p className="text-[10.5px] leading-[15px] font-medium text-mute">{label}</p>}
      {children && <p className="text-[12.5px] leading-[19px] text-ink2">{children}</p>}
      {hint && <p className="text-[11px] leading-[16px] text-mute">{hint}</p>}
    </div>
  )
}

async function copy(text: string) {
  const ok = await copyText(text)
  toast.show(
    ok
      ? { kind: 'done', title: '복사했어요', desc: text }
      : { kind: 'error', title: '복사하지 못했어요', desc: '직접 골라서 복사해 주세요.' },
  )
}

interface ActionCardProps {
  action: EventAction
  // 실행 대기에서 "게시했습니다"처럼 밖에서 직접 끝냈다고 알릴 때
  onComplete?: (action: EventAction) => void
}

export function ActionCard({ action, onComplete }: ActionCardProps) {
  const status = action.status
  const type = action.type
  const question = type === 'CONFIRMATION'
  const chip = STATUS_CHIP[status]
  // "김지훈 · 회장 · 3/9 15:30". 처리한 사람은 늘 남기고, 시각은 있을 때만 붙인다.
  const by = [
    formatResolver(action.resolvedBy),
    action.resolvedAt && formatDateTime(action.resolvedAt),
  ]
    .filter(Boolean)
    .join(' · ')

  let body: ReactNode = null
  if (status === 'PENDING') {
    body = (
      <>
        {action.content && (
          <Box label={question ? '토리가 모르는 것' : '토리가 준비한 초안'}>{action.content}</Box>
        )}
        {/* TODO: 결정 검토 모달 · 답변 입력 모달(#82)이 생기면 연다 */}
        <div className="flex items-center gap-[8px]">
          <Button>{question ? '답변하기' : '검토하기'}</Button>
          <span className="text-[11px] text-mute">
            {question ? '답변하면 바로 완료로 가요' : '승인 전에는 실행하지 않아요'}
          </span>
        </div>
      </>
    )
  } else if (status === 'APPROVED' && type !== 'CONFIRMATION') {
    const step = APPROVED_STEP[type]
    const content = action.content
    body = (
      <>
        {/* 내용이 없으면 안내 한 줄만 남기고, 복사할 게 없으니 복사 버튼도 숨긴다 */}
        <Box label={content ? '승인된 내용' : undefined} hint={step.hint}>
          {content}
        </Box>
        <div className="flex gap-[8px]">
          {/* TODO: 조건 보기 · 항목 보기는 결정 검토 모달(#82)이 생기면 연다 */}
          {(content || !step.copy) && (
            <Button variant="secondary" onClick={content ? () => copy(content) : undefined}>
              {step.secondary}
            </Button>
          )}
          <Button onClick={() => onComplete?.(action)}>{step.primary}</Button>
        </div>
      </>
    )
  } else if (status === 'DONE') {
    body =
      type === 'CONFIRMATION' ? (
        // 답이 안 오면 다른 완료 카드처럼 한 줄만 남긴다
        action.answer ? (
          <Box label={`답변 · ${by}`} hint="토리가 계획에 반영했어요">
            {action.answer}
          </Box>
        ) : (
          <Box>답변함 · {by}</Box>
        )
      ) : (
        <Box>
          {DONE_LABEL[type]} · {by}
        </Box>
      )
  } else if (status === 'DENIED') {
    body = action.denyReason && <Box label="진행하지 않기로 한 이유">{action.denyReason}</Box>
  } else if (status === 'FAILED') {
    body = (
      <>
        {action.failReason && <Box label="처리하지 못한 이유">{action.failReason}</Box>}
        {/* TODO(연동): 다시 시도 API가 생기면 연결한다 */}
        <div>
          <Button variant="secondary">다시 시도</Button>
        </div>
      </>
    )
  }

  return (
    <article className="flex flex-col gap-[10px] rounded-[14px] border border-line bg-card px-[18px] py-[16px]">
      <div className="flex items-center justify-between">
        <div className="flex gap-[7px]">
          <Chip size="sm">{ACTION_TYPE_LABEL[type] ?? type}</Chip>
          <Chip size="sm" tone={chip.tone}>
            {(question && QUESTION_CHIP[status]) || chip.label}
          </Chip>
        </div>
        {action.dueDate && (
          <span className="text-[11px] text-mute">기한 {formatMonthDay(action.dueDate)}</span>
        )}
      </div>
      <p className="text-[15px] leading-[22px] font-bold">{action.title}</p>
      {action.subtitle && <p className="text-[12px] leading-[18px] text-mute">{action.subtitle}</p>}
      {body}
    </article>
  )
}
