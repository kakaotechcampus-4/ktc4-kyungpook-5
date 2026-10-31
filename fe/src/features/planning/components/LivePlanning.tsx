// 행사 계획(라이브). P1에서 토리와 조건만 잡고, 초안을 만들면 P2에서 단계 흐름·세부 수정·시작을 한다.
// 두 단계는 같은 주소에서 ?view=flow로만 나눈다. 새로고침·뒤로 가기에도 보던 단계에 남는다.
import { useRef, useState, type ReactNode } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import {
  planMetaLine,
  toPlanSteps,
  usePlanningChat,
  usePlanningDrafts,
  useStartEvent,
} from '@/features/planning/hooks'
import { PlanChat } from '@/features/planning/components/PlanChat'
import { PlanFacts } from '@/features/planning/components/PlanFacts'
import { PlanStepper } from '@/features/planning/components/PlanStepper'
import { PlanSummaryPanel } from '@/features/planning/components/PlanSummaryPanel'
import { StepDetailModal } from '@/features/planning/components/StepDetailModal'
import { StepFlow } from '@/features/planning/components/StepFlow'
import { PLAN_FACT_KEYS } from '@/features/planning/types'
import type { PlanFacts as Facts, PlanWarning } from '@/features/planning/types'
import type { components } from '@/shared/api/schema'
import { ApiError } from '@/shared/api/types'
import { useAuthStore } from '@/shared/auth/store'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Modal } from '@/shared/ui/Modal'
import { PlanGeneratingScreen } from '@/shared/ui/StateScreen'

type S = components['schemas']

const P1_DESC = '토리와 대화하면서 큰 틀을 잡습니다. 정해진 건 오른쪽에 쌓입니다.'

export function LivePlanning() {
  const clubId = useAuthStore((state) => state.clubId)
  const userId = useAuthStore((state) => state.me?.id)
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const failedText = typeof location.state?.failedText === 'string' ? location.state.failedText : ''
  const eventId = params.get('eventId')
  const flow = params.get('view') === 'flow'
  const drafts = usePlanningDrafts(clubId, userId)
  // 다른 계획을 고르면 P1부터 다시 본다.
  const select = (id: string | null, text?: string) =>
    setParams(id ? { eventId: id } : {}, { state: text ? { failedText: text } : null })
  const showFlow = (on: boolean) => {
    if (eventId) setParams(on ? { eventId, view: 'flow' } : { eventId })
  }
  // 계획 초안 목록은 계획 중(PLANNING)인 행사만 준다. 거기서 빠졌으면 이미 시작한 행사다.
  const started = Boolean(
    eventId && drafts.isSuccess && !drafts.data.some((draft) => draft.id === eventId),
  )
  if (!clubId) {
    return (
      <div className="flex flex-col gap-5">
        <PlanHeader desc={P1_DESC} />
        <Card className="p-5">로그인하고 소속을 선택해 주세요.</Card>
      </div>
    )
  }
  return (
    <Conversation
      key={`${userId}:${clubId}:${eventId ?? 'new'}`}
      clubId={clubId}
      eventId={eventId}
      flow={flow}
      started={started}
      onShowFlow={showFlow}
      onCreated={select}
      failedText={failedText}
      userId={userId}
      picker={
        <Card className="flex flex-wrap items-center gap-3 p-4">
          <label htmlFor="planning-draft">계획 이어보기</label>
          <select
            id="planning-draft"
            className="rounded border border-line p-2"
            value={eventId ?? ''}
            onChange={(event) => select(event.target.value || null)}
          >
            <option value="">새 계획</option>
            {drafts.data?.map((draft) => (
              <option key={draft.id} value={draft.id}>
                {draft.title} · {new Date(draft.createdAt).toLocaleDateString('ko-KR')}
              </option>
            ))}
            {eventId && drafts.data && !drafts.data.some((draft) => draft.id === eventId) && (
              <option value={eventId}>선택한 계획</option>
            )}
          </select>
          <Button variant="secondary" onClick={() => select(null)}>
            새 계획
          </Button>
          {drafts.isLoading && <span role="status">계획 목록을 불러오는 중이에요.</span>}
          {drafts.isError && (
            <span role="alert">
              계획 목록을 불러오지 못했어요.{' '}
              <button className="underline" onClick={() => void drafts.refetch()}>
                다시 시도
              </button>
            </span>
          )}
        </Card>
      }
    />
  )
}

function PlanHeader({ desc, actions }: { desc: string; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-[16px]">
      <div className="flex flex-col gap-[4px]">
        <h1 className="text-h1">행사 계획</h1>
        <p className="text-mute">{desc}</p>
      </div>
      {actions && <div className="flex flex-wrap gap-[9px]">{actions}</div>}
    </header>
  )
}

// 「이 조건으로 만들어요」 아래 표시. 잠정·나중에·미정인 것만 골라 보인다(P1-c).
// 값은 단위 없이 와서(「32」·「45000」) 항목 이름으로 적는다: 「예상 인원 잠정」·「장소 미정」.
function generatingMarks(facts: Facts): Array<{ label: string; tentative?: boolean }> {
  return PLAN_FACT_KEYS.flatMap((key) => {
    const status = facts[key]?.status ?? '미정'
    return status === '확정' ? [] : [{ label: `${key} ${status}`, tentative: status === '잠정' }]
  })
}

function Conversation({
  clubId,
  eventId,
  flow,
  started,
  onShowFlow,
  onCreated,
  failedText,
  userId,
  picker,
}: {
  clubId: string
  eventId: string | null
  flow: boolean
  started: boolean
  onShowFlow: (on: boolean) => void
  onCreated: (id: string, failedText?: string) => void
  failedText: string
  userId: string | undefined
  picker: ReactNode
}) {
  const navigate = useNavigate()
  const live = usePlanningChat(clubId, eventId, userId, onCreated)
  const [showFailure, setShowFailure] = useState(Boolean(failedText))
  const [generating, setGenerating] = useState(false)
  // 이미 만든 흐름을 다시 만들기 전에 묻는다. 고쳐 둔 일정·세부가 서버에서 통째로 바뀐다.
  const [confirmRegenerate, setConfirmRegenerate] = useState(false)
  // 「그만두기」를 눌러도 서버 작업은 계속된다. 끝났을 때 2단계로 끌고 가지 않으려고 기억한다.
  const cancelled = useRef(false)

  // 불러오지 못해도 계획 선택은 남겨 둔다. 그래야 다른 계획이나 새 계획으로 갈 수 있다.
  if (eventId && (live.snapshot.isLoading || live.snapshot.isError))
    return (
      <div className="flex flex-col gap-[20px]">
        <PlanHeader desc={P1_DESC} />
        {picker}
        {live.snapshot.isLoading ? (
          <Card className="p-5" role="status">
            저장된 계획을 불러오는 중이에요.
          </Card>
        ) : (
          <Card className="p-5" role="alert">
            저장된 계획을 불러오지 못했어요. 권한과 연결을 확인해 주세요.{' '}
            <button className="underline" onClick={() => void live.snapshot.refetch()}>
              다시 시도
            </button>
          </Card>
        )}
      </div>
    )

  const screen = live.snapshot.data?.screen
  const steps = live.snapshot.data?.steps ?? []
  const lookup = live.view?.recordLookup
  const readiness = live.view?.generationReadiness ?? screen?.generationReadiness ?? null
  const lastMessage = live.snapshot.data?.messages.at(-1)
  const meta = screen ? planMetaLine(live.view?.draft.conditions ?? screen.draft.conditions) : ''

  if (generating) {
    return (
      <PlanGeneratingScreen
        conditionLine={meta || '지금까지 정한 조건으로'}
        marks={generatingMarks(live.facts)}
        onCancel={() => {
          cancelled.current = true
          setGenerating(false)
        }}
      />
    )
  }

  const generate = async () => {
    cancelled.current = false
    setGenerating(true)
    const generated = await live.generate()
    setGenerating(false)
    if (generated && !cancelled.current) onShowFlow(true)
  }

  // P2는 만들어 둔 단계가 있을 때만 있다(Figma 「P2 — 초기 화면 없음」).
  if (flow && eventId && screen && steps.length > 0) {
    return (
      <div className="flex flex-col gap-[20px]">
        <PlanHeader
          desc={meta || '행사 이름 · 인원 · 예산 · 기간'}
          actions={
            <>
              <Button variant="secondary" onClick={() => onShowFlow(false)}>
                1단계로 돌아가기
              </Button>
              <Button
                variant="secondary"
                onClick={() => navigate(`/planning/steps?eventId=${encodeURIComponent(eventId)}`)}
              >
                단계 넣고 빼기
              </Button>
            </>
          }
        />
        <PlanStepper current={2} />
        <PlanFlow eventId={eventId} steps={steps} screen={screen} started={started} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-[20px]">
      <PlanHeader desc={P1_DESC} />
      <PlanStepper current={1} />
      {picker}
      <div className="flex flex-col items-start gap-5 lg:flex-row">
        <PlanChat
          messages={live.messages}
          onSend={async (text) => {
            const success = await live.send(text)
            if (success) setShowFailure(false)
            return success
          }}
          busy={live.busy}
          error={
            live.error ||
            (showFailure ? '이전 요청 결과를 확인해 주세요. 서버에 반영됐을 수 있어요.' : '')
          }
          persisted={!!eventId}
          initialDraft={failedText}
        />
        <div className="flex w-full min-w-0 flex-col gap-4 lg:w-[340px] lg:shrink-0">
          {lastMessage?.role === 'USER' && !live.busy && (
            <p role="alert" className="text-failed">
              마지막 답변에 대한 질문을 받지 못했어요. 연결 상태를 확인해 주세요.
            </p>
          )}
          {lookup && (
            <p role="status" className="text-mute">
              {lookup.status === 'available'
                ? '관련 자료를 참고했어요.'
                : lookup.status === 'not_found'
                  ? '관련 자료를 찾지 못했어요.'
                  : lookup.status === 'failed'
                    ? '자료 검색에 실패했어요.'
                    : '자료 조회를 진행하지 못했어요.'}
            </p>
          )}
          <PlanFacts
            facts={live.facts}
            readiness={{
              canGenerate: Boolean(eventId && readiness?.canGenerate && !live.busy),
              // 막힌 이유가 서버 사유가 아닐 때도 빈칸으로 두지 않는다(PlanFacts BLOCK_TEXT).
              reasons: live.busy
                ? ['answering']
                : !eventId
                  ? ['event_type_missing']
                  : (readiness?.reasons ?? ['readiness_unknown']),
            }}
            nextLabel={steps.length > 0 ? '지금 조건으로 다시 만들기' : undefined}
            onView={steps.length > 0 ? () => onShowFlow(true) : undefined}
            onNext={() => (steps.length > 0 ? setConfirmRegenerate(true) : void generate())}
          />
        </div>
      </div>
      <Modal
        open={confirmRegenerate}
        onClose={() => setConfirmRegenerate(false)}
        title="흐름을 다시 만들까요?"
        chip={<Chip tone="failed">되돌릴 수 없음</Chip>}
        width={520}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmRegenerate(false)}>
              돌아가기
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setConfirmRegenerate(false)
                void generate()
              }}
            >
              다시 만들기
            </Button>
          </>
        }
      >
        <p className="text-[13px] leading-[20px] text-ink2">
          지금 조건으로 단계를 새로 만들어요. 만들어 둔 {steps.length}개 단계와 고쳐 둔 일정·세부
          내용은 새 결과로 바뀌어요.
        </p>
      </Modal>
    </div>
  )
}

// P2: 단계 흐름(왼쪽)과 요약·주의·시작(오른쪽). Figma v13 「P2 흐름 만들기」.
function PlanFlow({
  eventId,
  steps,
  screen,
  started,
}: {
  eventId: string
  steps: S['PlannedStepOut'][]
  screen: S['PlanScreenOut']
  // 이미 시작한 행사면 시작 버튼을 잠근다(뒤로 가기로 돌아온 경우 등).
  started: boolean
}) {
  const navigate = useNavigate()
  const start = useStartEvent(eventId)
  const [editingId, setEditingId] = useState<string | null>(null)
  const editing = steps.find((step) => step.id === editingId) ?? null
  const toSteps = () => navigate(`/planning/steps?eventId=${encodeURIComponent(eventId)}`)
  // 서버 주의사항은 문장 목록이다. 제목·버튼은 Figma 문구를 그대로 쓴다.
  const warning: PlanWarning | undefined = screen.warnings.length
    ? {
        title: '시작 전에 확인해 주세요',
        body: screen.warnings.join(' '),
        actionLabel: '단계 수정하기',
      }
    : undefined

  // 성공 처리에서 난 오류를 「시작하지 못했어요」로 잘못 알리지 않게 then에 둘을 따로 건넨다.
  const startEvent = () =>
    start.mutateAsync().then(
      () => {
        toast.show({
          kind: 'done',
          title: '행사를 시작했어요',
          desc: '행사 목록에서 이어서 볼 수 있어요.',
        })
        navigate('/events')
      },
      (cause) =>
        toast.show({
          kind: 'error',
          title: '행사를 시작하지 못했어요',
          // 「행사 시작일이 필요합니다」처럼 무엇이 빠졌는지는 fields에 온다. 있으면 그게 더 정확하다.
          desc:
            cause instanceof ApiError
              ? (Object.values(cause.fields ?? {})[0] ?? cause.message)
              : '연결 상태를 확인해 주세요.',
        }),
    )

  return (
    <>
      <div className="flex flex-col gap-[20px] lg:flex-row lg:items-start">
        <StepFlow steps={toPlanSteps(steps)} onEditStep={(step) => setEditingId(step.id)} />
        {/* 수금·공지·준비 기간은 셀 방법이 정해지지 않아 서버 4줄만 넘기고 나머지는 「—」로 둔다. */}
        <PlanSummaryPanel
          summary={screen.summary}
          warning={warning}
          starting={start.isPending}
          started={started}
          onFixSteps={toSteps}
          onStart={() => void startEvent()}
        />
      </div>
      <StepDetailModal
        step={editing}
        onClose={() => setEditingId(null)}
        onSaved={() => setEditingId(null)}
      />
    </>
  )
}
