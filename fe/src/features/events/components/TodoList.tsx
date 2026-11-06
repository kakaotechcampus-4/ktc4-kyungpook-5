// 지금 할 일 카드(L2): 운영진 차례인 일을 행사 전체에서 모아 보인다.
// 토리가 쓴 초안은 여기서 바로 검토 모달을 연다. 승인은 원문을 다 볼 수 있는 검토 모달에서만 한다.
// 어떤 일을 어떤 순서로 보일지는 todo.ts가 정한다.
import type { ComponentProps, ReactNode } from 'react'
import { blanksLine, draftView } from '@/features/events/actionDraft'
import { APPROVED_STEP, copy } from '@/features/events/actionExecution'
import { DraftText, TypingDots } from '@/features/events/components/ActionCard'
import { toriSummary, type TodoItem, type TodoKind } from '@/features/events/todo'
import type { EventAction, EventStep } from '@/features/events/types'
import { cn } from '@/shared/lib/cn'
import { formatMonthDay } from '@/shared/lib/format'
import { ACTION_TYPE_LABEL } from '@/shared/lib/labels'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'
import { ToriNote } from '@/shared/ui/ToriNote'

const KIND_CHIP: Record<TodoKind, { label: string; tone: ComponentProps<typeof Chip>['tone'] }> = {
  drafting: { label: '토리가 쓰는 중', tone: 'approved' },
  draftFailed: { label: '초안 못 받음', tone: 'failed' },
  failed: { label: '실패', tone: 'failed' },
  question: { label: '답변 대기', tone: 'pending' },
  review: { label: '승인 대기', tone: 'pending' },
  manual: { label: '직접 처리', tone: 'pending' },
  execute: { label: '실행 대기', tone: 'approved' },
}

interface TodoListProps {
  items: TodoItem[]
  // 목록을 불러오지 못했으면 true. 빈 목록과 헷갈리지 않게 따로 알린다.
  failed?: boolean
  onRetry?: () => void
  // 승인 대기의 [검토하기] → 결정 검토 모달
  onReview: (action: EventAction) => void
  // 실행 대기의 [게시했습니다] 등 · 직접 처리의 [완료로 표시]
  onComplete: (action: EventAction) => void
  // 토리 질문의 선택지. choice는 options[].key, 직접 처리면 'MANUAL'
  onResolve: (action: EventAction, choice: string) => void
  // 초안 「다시 받기」와 지금 보내는 중인 Action id
  onRequestDraft: (action: EventAction) => void
  requestingDraftId?: string
  // 단계 이름을 누르면 Step 모달
  onOpenStep: (step: EventStep) => void
  readOnly?: boolean
  className?: string
}

export function TodoList({
  items,
  failed = false,
  onRetry,
  onReview,
  onComplete,
  onResolve,
  onRequestDraft,
  requestingDraftId,
  onOpenStep,
  readOnly = false,
  className,
}: TodoListProps) {
  const summary = toriSummary(items)
  const empty = items.length === 0

  return (
    <Card className={cn('flex flex-col', className)}>
      <div className="flex items-center gap-[9px] px-[26px] pt-[24px] pb-[16px]">
        <h2 className="text-h2">지금 할 일</h2>
        {!failed && <Chip tone={empty ? 'neutral' : 'approved'}>{items.length}건</Chip>}
      </div>

      {/* 토리가 무엇을 했는지 한 줄. 초안을 승인하거나 고치면 사라진다. */}
      {summary && (
        <div role="status" className="px-[26px] pb-[16px]">
          <ToriNote title={summaryTitle(summary)}>{summaryBody(summary)}</ToriNote>
        </div>
      )}

      {failed ? (
        <div className="px-[26px] pb-[26px]">
          <EmptyState
            variant="inline"
            toriSize={56}
            title="할 일을 불러오지 못했어요"
            desc="잠시 뒤에 다시 확인해 주세요."
            action={
              onRetry && (
                <Button variant="secondary" onClick={onRetry}>
                  다시 확인
                </Button>
              )
            }
          />
        </div>
      ) : empty ? (
        <div className="px-[26px] pb-[26px]">
          <EmptyState
            variant="inline"
            toriSize={56}
            title="지금 할 일이 없어요"
            desc={
              readOnly
                ? '진행 중인 행사에서만 할 일이 생겨요.'
                : '다음 단계가 시작되면 토리가 필요한 공지를 써 둘게요.'
            }
          />
        </div>
      ) : (
        <ul>
          {items.map((item) => (
            <TodoRow
              key={item.action.id}
              item={item}
              onReview={onReview}
              onComplete={onComplete}
              onResolve={onResolve}
              onRequestDraft={onRequestDraft}
              requestingDraft={requestingDraftId === item.action.id}
              onOpenStep={onOpenStep}
              readOnly={readOnly}
            />
          ))}
        </ul>
      )}
    </Card>
  )
}

function summaryTitle(s: NonNullable<ReturnType<typeof toriSummary>>) {
  return s.drafting > 0
    ? `토리가 글 ${s.drafting}건을 쓰고 있어요`
    : `토리가 초안 ${s.ready}건을 써 뒀어요`
}

function summaryBody(s: NonNullable<ReturnType<typeof toriSummary>>) {
  const where = s.stepName ? `「${s.stepName}」 단계에 쓸 글이에요. ` : ''
  if (s.drafting > 0)
    return `${where}다 쓰면 아래 목록에 바로 보여요.${s.ready > 0 ? ` 먼저 써 둔 초안 ${s.ready}건은 지금 검토할 수 있어요.` : ''}`
  return `${where}검토하고 승인하면 복사해서 올릴 수 있어요.${s.blanks > 0 ? ` 빈칸 ${s.blanks}곳은 직접 채워 주세요.` : ''}`
}

interface TodoRowProps {
  item: TodoItem
  onReview: (action: EventAction) => void
  onComplete: (action: EventAction) => void
  onResolve: (action: EventAction, choice: string) => void
  onRequestDraft: (action: EventAction) => void
  requestingDraft: boolean
  onOpenStep: (step: EventStep) => void
  readOnly: boolean
}

function TodoRow({
  item,
  onReview,
  onComplete,
  onResolve,
  onRequestDraft,
  requestingDraft,
  onOpenStep,
  readOnly,
}: TodoRowProps) {
  const { kind, action, step, position } = item
  const chip = KIND_CHIP[kind]

  let detail: ReactNode = null
  let buttons: ReactNode = null
  switch (kind) {
    case 'drafting':
      detail = (
        <p className="flex items-center gap-[8px] text-[12.5px] leading-[19px] text-ink2">
          토리가 초안을 쓰고 있어요
          <TypingDots />
        </p>
      )
      break
    case 'draftFailed':
      detail = <Line>토리가 초안을 쓰지 못했어요. 다시 받거나, 검토하기에서 직접 써도 돼요.</Line>
      buttons = (
        <>
          <Button disabled={readOnly} onClick={() => onReview(action)}>
            검토하기
          </Button>
          {action.canRequestDraft && (
            <Button
              variant="secondary"
              disabled={readOnly}
              loading={requestingDraft}
              onClick={() => onRequestDraft(action)}
            >
              다시 받기
            </Button>
          )}
        </>
      )
      break
    case 'review': {
      const view = draftView(action)
      const draft = (view === 'READY_AI' || view === 'READY_USER') && action.content
      detail = draft ? (
        <Preview
          text={draft}
          note={[
            view === 'READY_USER' ? '직접 고친 글' : '토리 초안',
            blanksLine(action.contentUnknowns),
          ]}
        />
      ) : (
        action.subtitle && <Line muted>{action.subtitle}</Line>
      )
      buttons = (
        <Button disabled={readOnly} onClick={() => onReview(action)}>
          검토하기
        </Button>
      )
      break
    }
    case 'manual':
      detail = <Line muted>{action.subtitle ?? '직접 처리한 뒤 완료로 표시해 주세요.'}</Line>
      buttons = (
        <Button disabled={readOnly} onClick={() => onComplete(action)}>
          완료로 표시
        </Button>
      )
      break
    case 'execute': {
      if (action.type === 'CONFIRMATION') break
      const next = APPROVED_STEP[action.type]
      const content = action.content
      detail = <Line muted>승인됐어요. {next.hint}.</Line>
      buttons = (
        <>
          {next.copy && content && (
            <Button variant="secondary" onClick={() => void copy(content)}>
              {next.secondary}
            </Button>
          )}
          <Button disabled={readOnly} onClick={() => onComplete(action)}>
            {next.primary}
          </Button>
        </>
      )
      break
    }
    case 'question':
      detail = (action.subtitle ?? action.content) && (
        <Line>{action.subtitle ?? action.content}</Line>
      )
      buttons = (
        <>
          {/* 첫 선택지가 토리가 가장 그럴듯하다고 본 답이라 파랗게 둔다 */}
          {(action.options ?? []).map((option, i) => (
            <Button
              key={option.key}
              variant={i === 0 ? 'primary' : 'secondary'}
              disabled={readOnly}
              onClick={() => onResolve(action, option.key)}
            >
              {option.label}
            </Button>
          ))}
          {action.allowManual && (
            <Button
              variant="secondary"
              disabled={readOnly}
              onClick={() => onResolve(action, 'MANUAL')}
            >
              직접 처리
            </Button>
          )}
        </>
      )
      break
    case 'failed':
      detail = (
        <Line>{action.failReason ?? '처리하지 못했어요. 단계에서 자세히 확인해 주세요.'}</Line>
      )
      if (step)
        buttons = (
          <Button variant="secondary" onClick={() => onOpenStep(step)}>
            단계에서 보기
          </Button>
        )
      break
  }

  return (
    <li className="flex flex-col gap-[10px] border-t border-line px-[26px] py-[17px]">
      <div className="flex flex-wrap items-center gap-x-[7px] gap-y-[6px]">
        <Chip size="sm">
          {/* 확인 요청은 토리가 묻는 질문이라 여기서는 그렇게 부른다 */}
          {action.type === 'CONFIRMATION'
            ? '토리 질문'
            : (ACTION_TYPE_LABEL[action.type] ?? action.type)}
        </Chip>
        <Chip size="sm" tone={chip.tone}>
          {chip.label}
        </Chip>
        {step && (
          <button
            type="button"
            onClick={() => onOpenStep(step)}
            aria-label={`${position}. ${step.name} 단계 열기`}
            className="rounded-[4px] text-[11.5px] font-medium text-mute underline-offset-2 hover:text-ink2 hover:underline focus-visible:outline-2 focus-visible:outline-blue-400"
          >
            {position}. {step.name}
          </button>
        )}
        {action.dueDate && (
          <span className="ml-auto text-[11px] text-mute">
            기한 {formatMonthDay(action.dueDate)}
          </span>
        )}
      </div>
      <p className="text-[14.5px] leading-[21px] font-bold break-words">{action.title}</p>
      {detail}
      {buttons && <div className="flex flex-wrap items-center gap-[8px]">{buttons}</div>}
    </li>
  )
}

function Line({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return (
    <p
      className={cn('text-[12.5px] leading-[19px] break-words', muted ? 'text-mute' : 'text-ink2')}
    >
      {children}
    </p>
  )
}

// 초안 미리보기 세 줄. 초안이 도착하는 순간 한 번 떠오른다(움직임 줄이기면 그대로).
function Preview({ text, note }: { text: string; note: Array<string | undefined> }) {
  return (
    <div className="flex min-w-0 animate-turn-in flex-col gap-[6px] rounded-[11px] bg-bg px-[14px] py-[12px] motion-reduce:animate-none">
      <p className="line-clamp-3 text-[12.5px] leading-[19px] break-words whitespace-pre-line text-ink2">
        {/* 초안은 제목 다음에 빈 줄을 두는 일이 많아, 미리보기에서만 빈 줄을 접어 본문을 한 줄 더 보인다 */}
        <DraftText text={text.replace(/\n[ \t]*(?:\n[ \t]*)+/g, '\n')} />
      </p>
      <p className="text-[11px] leading-[16px] text-mute">{note.filter(Boolean).join(' · ')}</p>
    </div>
  )
}
