// Action 카드(Step 모달 안): 유형 · 상태 · 기한 / 제목 · 설명 / 회색 박스 / 버튼.
// 상태(ActionStatus)마다 박스 문구와 버튼이 바뀌고, 실행 대기 버튼은 유형마다 다르다.
// 승인·진행하지 않기는 카드가 아니라 [검토하기]로 여는 결정 검토 모달에서 한다.
// 공지·발송 카드의 승인 대기 박스는 토리 초안 상태(#335)에 따라 바뀐다.
import type { ComponentProps, ReactNode } from 'react'
import {
  blanksLine,
  draftView,
  isDraftTarget,
  splitBlanks,
  type DraftView,
} from '@/features/events/actionDraft'
import { APPROVED_STEP, copy, type DoableType } from '@/features/events/actionExecution'
import type { ActionStatus, EventAction, StepState } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { formatDateTime, formatMonthDay } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL, formatResolver } from '@/shared/lib/labels'
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

// 완료 기록의 첫머리
const DONE_LABEL: Record<DoableType, string> = {
  NOTICE: '단톡방에 게시함',
  EXTERNAL_SEND: '발송함',
  CONTRACT: '계약서 등록함',
  TRANSFER: '이체 기록함',
  EXPENSE: '장부에 반영함',
}

// 회색 박스: 작은 제목 · 본문 · 안내 줄. 없는 줄은 그리지 않는다.
// 본문은 줄바꿈을 살리고, 띄어쓰기 없는 긴 링크도 칸 안에서 끊는다. clamp면 미리보기로 6줄까지만 보인다.
function Box({
  label,
  children,
  hint,
  clamp = false,
}: {
  label?: string
  children?: ReactNode
  hint?: string | Array<string | undefined>
  clamp?: boolean
}) {
  const hints = (Array.isArray(hint) ? hint : [hint]).filter(Boolean)
  return (
    <div className="flex min-w-0 flex-col gap-[5px] rounded-[11px] bg-bg px-[14px] py-[12px]">
      {label && <p className="text-[10.5px] leading-[15px] font-medium text-mute">{label}</p>}
      {children && (
        <p
          className={cn(
            'text-[12.5px] leading-[19px] break-words whitespace-pre-line text-ink2',
            clamp && 'line-clamp-6',
          )}
        >
          {children}
        </p>
      )}
      {hints.map((line) => (
        <p key={line} className="text-[11px] leading-[16px] text-mute">
          {line}
        </p>
      ))}
    </div>
  )
}

// 초안 본문. 운영진이 채울 [ ] 자리를 칠해 「비워 둔 곳」과 바로 맞춰 볼 수 있게 한다.
// L2 지금 할 일의 미리보기도 같은 모양을 쓴다.
export function DraftText({ text }: { text: string }) {
  return splitBlanks(text).map((part, i) =>
    part.blank ? (
      <mark key={i} className="rounded-[4px] bg-pending-bg px-[2px] text-pending">
        {part.text}
      </mark>
    ) : (
      part.text
    ),
  )
}

// 토리가 쓰는 중. P1 대화의 입력 중 표시(PlanChat TypingDots)와 같은 점 세 개다.
// 움직임 줄이기 설정이면 점이 멈춘 채로 보인다.
function DraftingBox() {
  return (
    <div
      role="status"
      className="flex items-center gap-[8px] rounded-[11px] bg-bg px-[14px] py-[12px] text-[12.5px] leading-[19px] text-ink2"
    >
      토리가 초안을 쓰고 있어요
      <TypingDots />
    </div>
  )
}

// 점 세 개. 움직임 줄이기 설정이면 멈춘 채로 보인다. L2 지금 할 일에서도 쓴다.
export function TypingDots() {
  return (
    <span aria-hidden className="flex h-[19px] items-center gap-[4px]">
      {['0ms', '150ms', '300ms'].map((delay) => (
        <span
          key={delay}
          style={{ animationDelay: delay }}
          className="size-[5px] rounded-full bg-mute animate-typing-dot motion-reduce:animate-none"
        />
      ))}
    </span>
  )
}

// 승인 대기 카드의 박스 자리
function PendingBox({ action, view, question }: { action: EventAction; view: DraftView; question: boolean }) {
  const content = action.content
  switch (view) {
    case 'DRAFTING':
      return <DraftingBox />
    case 'FAILED':
      return (
        <Box hint="다시 받거나, 검토하기에서 직접 써도 돼요">초안을 받지 못했어요</Box>
      )
    case 'READY_AI':
    case 'READY_USER':
      return content ? (
        <Box
          clamp
          label={view === 'READY_USER' ? '직접 고친 내용' : '토리가 준비한 초안'}
          hint={[
            blanksLine(action.contentUnknowns),
            view === 'READY_USER' ? '고친 글을 덮어쓰지 않게 토리가 다시 쓰지 않아요' : undefined,
          ]}
        >
          <DraftText text={content} />
        </Box>
      ) : null
    case 'UPCOMING':
      return <p className="text-[12px] leading-[18px] text-mute">이 단계가 시작되면 토리가 초안을 써요</p>
    default:
      // 초안 상태가 없는 이전 응답 · 확인 요청은 지금과 같다
      return content ? (
        <Box label={question ? '토리가 모르는 것' : '토리가 준비한 초안'}>
          {content}
        </Box>
      ) : null
  }
}

interface ActionCardProps {
  action: EventAction
  // 실행 대기에서 "게시했습니다"처럼 밖에서 직접 끝냈다고 알릴 때
  onComplete?: (action: EventAction) => void
  // 승인 대기에서 [검토하기] · [답변하기]를 눌렀을 때. 실행 대기 공지의 [내용 고치기]도 같은 모달을 연다.
  // 모달은 화면 쪽에서 띄운다.
  onReview?: (action: EventAction) => void
  // 토리 초안 「다시 받기」. 서버가 canRequestDraft로 허락할 때만 버튼이 보인다.
  onRequestDraft?: (action: EventAction) => void
  // 「다시 받기」를 보내고 기다리는 중
  requestingDraft?: boolean
  // 이 Action이 속한 단계의 상태. 아직 시작 안 한 단계(TODO)면 초안이 오기 전이라고 알린다.
  stepState?: StepState
  readOnly?: boolean
}

export function ActionCard({
  action,
  onComplete,
  onReview,
  onRequestDraft,
  requestingDraft = false,
  stepState,
  readOnly = false,
}: ActionCardProps) {
  const status = action.status
  const type = action.type
  const question = type === 'CONFIRMATION'
  const view = draftView(action, stepState)
  const canRedraft =
    !!onRequestDraft && !!action.canRequestDraft && (view === 'READY_AI' || view === 'FAILED')
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
        <PendingBox action={action} view={view} question={question} />
        <div className="flex flex-wrap items-center gap-[8px]">
          <Button disabled={readOnly} onClick={() => !question && action.approveNeeded === false ? onComplete?.(action) : onReview?.(action)}>
            {question ? '답변하기' : action.approveNeeded === false ? '완료로 표시' : '검토하기'}
          </Button>
          {canRedraft && (
            <Button
              variant="secondary"
              disabled={readOnly}
              loading={requestingDraft}
              onClick={() => onRequestDraft?.(action)}
            >
              {view === 'FAILED' ? '다시 받기' : '초안 다시 받기'}
            </Button>
          )}
          <span className="text-[11px] text-mute">
            {question ? '답변하면 바로 완료로 가요' : action.approveNeeded === false ? '직접 처리한 후 완료로 표시해 주세요' : '승인 전에는 실행하지 않아요'}
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
        <div className="flex flex-wrap gap-[8px]">
          {/* 승인 뒤에도 고칠 수 있다. 저장하면 서버가 승인 대기로 되돌린다(#335). */}
          {isDraftTarget(type) && onReview && (
            <Button variant="ghost" disabled={readOnly} onClick={() => onReview(action)}>
              {content ? '내용 고치기' : '내용 쓰기'}
            </Button>
          )}
          {(content || !step.copy) && (
            <Button
              variant="secondary"
              onClick={content ? () => copy(content) : () => onReview?.(action)}
            >
              {step.secondary}
            </Button>
          )}
          <Button disabled={readOnly} onClick={() => onComplete?.(action)}>
            {step.primary}
          </Button>
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
          <Button variant="secondary" disabled>
            다시 시도
          </Button>
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
