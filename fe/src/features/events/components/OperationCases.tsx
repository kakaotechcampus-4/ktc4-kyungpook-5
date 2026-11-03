import { useRef, useState, type FormEvent } from 'react'
import { useAuthStore } from '@/shared/auth/store'
import { ApiError } from '@/shared/api/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Textarea } from '@/shared/ui/Input'
import { AnswerModal } from './AnswerModal'
import { useResolveAction } from '../hooks'
import { useOperationCaseActions } from '../operationCasesHooks'
import type { OperationCase } from '../operationCasesApi'
import type { EventAction } from '../types'

function message(error: unknown) {
  if (error instanceof ApiError && error.code === 'OPERATION_IN_PROGRESS')
    return '이미 처리 중이에요. 잠시 뒤 다시 확인해 주세요.'
  if (error instanceof ApiError && error.code === 'FORBIDDEN')
    return '이 행사에서 처리할 권한이 없어요.'
  return '처리하지 못했어요. 연결과 행사 상태를 확인한 뒤 다시 시도해 주세요.'
}

export function OperationCases({
  eventId,
  active,
  cases,
  loading,
  error,
  onReload,
}: {
  eventId: string
  active: boolean
  cases: OperationCase[]
  loading: boolean
  error: boolean
  onReload: () => void
}) {
  const user = useAuthStore((state) => state.user)
  const editable = active && !!user
  const [draft, setDraft] = useState('')
  const [errorText, setErrorText] = useState('')
  const [caseErrors, setCaseErrors] = useState<
    Record<string, { kind: 'question' | 'result'; text: string }>
  >({})
  const [selected, setSelected] = useState<OperationCase | null>(null)
  const [answerError, setAnswerError] = useState('')
  const request = useRef<{ text: string; id: string } | null>(null)
  const locked = useRef(false)
  const actions = useOperationCaseActions(eventId)
  const resolve = useResolveAction()
  const busy =
    actions.create.isPending ||
    actions.question.isPending ||
    actions.result.isPending ||
    actions.recover.isPending ||
    resolve.isPending
  const setCaseError = (id: string, kind: 'question' | 'result', text: string) =>
    setCaseErrors((previous) => ({ ...previous, [id]: { kind, text } }))

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const situation = draft.trim()
    if (!editable || !situation || locked.current) return
    locked.current = true
    if (!request.current || request.current.text !== situation)
      request.current = { text: situation, id: crypto.randomUUID() }
    setErrorText('')
    try {
      await actions.create.mutateAsync({ situation, clientRequestId: request.current.id })
      request.current = null
      setDraft('')
    } catch (cause) {
      setErrorText(message(cause))
    } finally {
      locked.current = false
    }
  }
  const runCase = async (item: OperationCase, kind: 'question' | 'result') => {
    setCaseError(item.id, kind, '')
    try {
      await (kind === 'question'
        ? actions.question.mutateAsync(item.id)
        : actions.result.mutateAsync(item.id))
    } catch (cause) {
      setCaseError(item.id, kind, message(cause))
    }
  }
  const answer = async (action: EventAction, choice: string, manualValue?: string) => {
    const item = selected
    if (!item || !editable) return false
    setAnswerError('')
    try {
      await resolve.mutateAsync({ action, choice, manualValue })
      setSelected(null)
      void runCase(item, 'result')
      return true
    } catch {
      try {
        const saved = await actions.recover.mutateAsync(item.id)
        const same =
          saved.action?.status === 'DONE' &&
          saved.action.resolvedChoice === choice &&
          (choice !== 'MANUAL' || saved.action.manualValue === manualValue)
        if (same) {
          setSelected(null)
          if (saved.resultStatus !== 'READY') void runCase(saved, 'result')
          return true
        }
        if (saved.action?.status === 'DONE')
          setAnswerError(
            '다른 답변이 이미 저장됐어요. 입력한 내용을 확인하고 창을 닫아 최신 결과를 확인해 주세요.',
          )
        else if (saved.action?.version !== action.version)
          setAnswerError(
            '질문이 변경됐어요. 입력한 내용을 확인하고 창을 닫아 최신 질문을 다시 열어 주세요.',
          )
      } catch {
        /* 입력은 모달에 남기고 다시 시도할 수 있다. */
      }
      return false
    }
  }
  return (
    <Card className="space-y-4 p-5">
      <div>
        <h2 className="text-h2">운영 상황을 알려주세요</h2>
        <p className="mt-1 text-caption text-ink2">
          바뀐 상황을 살펴보고 필요한 질문과 제안을 정리해요.
        </p>
      </div>
      {editable ? (
        <form className="space-y-3" onSubmit={(event) => void submit(event)}>
          <Textarea
            label="현재 상황"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={4000}
            disabled={busy}
            placeholder="예: 행사 장소 예약이 어려워졌어요"
          />
          {errorText && (
            <p role="alert" className="text-caption text-failed">
              {errorText}
            </p>
          )}
          <Button type="submit" disabled={busy || !draft.trim()}>
            {actions.create.isPending ? '확인 중…' : '상황 확인하기'}
          </Button>
        </form>
      ) : (
        <p className="text-caption text-mute">
          진행 중인 행사에서 운영진이 상황을 입력할 수 있어요.
        </p>
      )}
      {loading && (
        <p role="status" className="text-caption text-mute">
          저장된 상황을 불러오고 있어요.
        </p>
      )}
      {error && (
        <p role="alert" className="text-caption text-failed">
          저장된 상황을 불러오지 못했어요.{' '}
          <button type="button" className="underline" onClick={onReload}>
            다시 확인
          </button>
        </p>
      )}
      {cases.length > 0 && (
        <ul className="space-y-4 border-t border-line pt-4">
          {cases.map((item) => {
            const action = item.action
            const answered = action?.status === 'DONE'
            const answerText =
              action?.resolvedChoice === 'MANUAL'
                ? action.manualValue
                : action?.options?.find((option) => option.key === action.resolvedChoice)?.label
            const waiting =
              item.questionStatus === 'PENDING' ||
              item.questionStatus === 'PROCESSING' ||
              item.resultStatus === 'PROCESSING'
            const issue = caseErrors[item.id]
            const caseError =
              issue?.kind === 'question'
                ? item.questionStatus === 'FAILED' || item.questionStatus === 'PENDING'
                  ? issue.text
                  : ''
                : item.resultStatus === 'FAILED' || item.resultStatus === 'NOT_REQUESTED'
                  ? issue?.text
                  : ''
            return (
              <li
                key={item.id}
                className="space-y-2 border-b border-line pb-4 last:border-0 last:pb-0"
              >
                <p className="text-caption font-semibold text-ink2">입력한 상황</p>
                <p className="whitespace-pre-wrap break-words">{item.situation}</p>
                {waiting && (
                  <p role="status" className="text-caption text-mute">
                    토리가 확인하고 있어요…{' '}
                    <button type="button" className="underline" onClick={onReload}>
                      상태 다시 확인
                    </button>
                  </p>
                )}
                {item.questionStatus === 'FAILED' && (
                  <p className="text-caption text-failed">질문을 준비하지 못했어요.</p>
                )}
                {(item.questionStatus === 'PENDING' || item.questionStatus === 'FAILED') &&
                  editable && (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={busy}
                      onClick={() => void runCase(item, 'question')}
                    >
                      질문 다시 확인
                    </Button>
                  )}
                {action && (
                  <div className="space-y-2 rounded-lg bg-bg p-3">
                    <p className="text-caption font-semibold text-ink2">토리의 질문</p>
                    <p className="whitespace-pre-wrap break-words">
                      {action.content || action.title}
                    </p>
                    {answered ? (
                      <p className="text-caption text-ink2">
                        저장된 답변 · {answerText || '저장된 답변을 확인할 수 없어요.'}
                      </p>
                    ) : (
                      editable &&
                      item.questionStatus === 'NEEDS_ANSWER' && (
                        <Button
                          size="sm"
                          disabled={busy}
                          onClick={() => {
                            setAnswerError('')
                            setSelected(item)
                          }}
                        >
                          답변하기
                        </Button>
                      )
                    )}
                  </div>
                )}
                {item.resultStatus === 'FAILED' && (
                  <p className="text-caption text-failed">
                    결과를 만들지 못했어요. 저장된 답변은 유지돼요.
                  </p>
                )}
                {caseError && (
                  <p role="alert" className="text-caption text-failed">
                    {caseError}
                  </p>
                )}
                {answered &&
                  (item.resultStatus === 'FAILED' ||
                    item.resultStatus === 'NOT_REQUESTED' ||
                    !!caseError) &&
                  editable && (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={busy}
                      onClick={() => void runCase(item, 'result')}
                    >
                      결과 다시 만들기
                    </Button>
                  )}
                {item.result && item.resultStatus === 'READY' && (
                  <div className="space-y-2">
                    <p className="text-caption font-semibold text-ink2">확인 결과</p>
                    <p className="whitespace-pre-wrap break-words">{item.result.summary}</p>
                    {item.result.suggestions.length > 0 && (
                      <>
                        <p className="text-caption font-semibold text-ink2">검토할 제안</p>
                        <ul className="list-disc space-y-1 pl-5">
                          {item.result.suggestions.map((suggestion, index) => (
                            <li key={index} className="break-words">
                              {suggestion}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                    <p className="text-caption text-mute">
                      제안은 아직 적용되거나 발송되지 않았어요.
                    </p>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <AnswerModal
        action={
          selected?.action
            ? { ...selected.action, title: selected.action.content || selected.action.title }
            : undefined
        }
        onClose={() => setSelected(null)}
        onAnswer={answer}
        pending={resolve.isPending || actions.recover.isPending}
        operationCase
        errorMessage={answerError}
        readOnly={!editable}
      />
    </Card>
  )
}
