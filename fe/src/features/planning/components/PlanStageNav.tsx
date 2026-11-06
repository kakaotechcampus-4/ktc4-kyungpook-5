// 행사 조건 ↔ 계획 검토를 오가는 두 칸 토글.
//
// 전에는 "① 행사 조건 → ② 계획 검토"라고 적힌 안내문이었고, 오가는 길은 화면마다
// 흩어진 작은 글자 링크(「기존 초안 검토하기」·「행사 조건 수정」)였다. 두 화면을
// 오가는 것이 이 기능의 주된 움직임이라, 안내문 자리를 그대로 이동 수단으로 바꿨다.
//
// 대화창과 같은 너비로 두고, 지금 보고 있는 쪽을 파란 칸으로 채운다.
// 파란 칸은 하나만 두고 위치만 바꾼다. 화면이 바뀔 때 View Transitions가 이 칸을
// 「행사 조건」에서 「계획 검토」로 미끄러지게 한다(index.css의 plan-stage-pill).
import { Link } from 'react-router-dom'
import { cn } from '@/shared/lib/cn'

type Stage = 'conditions' | 'review'

const LABEL: Record<Stage, string> = { conditions: '행사 조건', review: '계획 검토' }
const STAGES: Stage[] = ['conditions', 'review']
// 토글 글자를 파란 칸과 따로 찍는 이름. 칸이 지나가는 동안 글자가 칸 아래로 묻히지 않는다.
const LABEL_TRANSITION: Record<Stage, string> = {
  conditions: '[view-transition-name:plan-stage-conditions]',
  review: '[view-transition-name:plan-stage-review]',
}

const SEGMENT =
  'relative flex min-h-11 flex-1 items-center justify-center gap-2 rounded-[8px] px-3 text-[13.5px] font-bold transition-colors duration-150 motion-reduce:transition-none'

export function PlanStageNav({
  current,
  eventId,
  // 초안이 없으면 계획 검토에 볼 것이 없다. 눌러도 되돌아오므로 아예 잠근다.
  canReview = false,
  // 초안 생성 화면에서만 쓴다. making: 계획 검토 칸에 「만드는 중」, ready: 막 열린 칸을 옅게 칠한다.
  generation,
}: {
  current: Stage
  eventId?: string | null
  canReview?: boolean
  generation?: 'making' | 'ready'
}) {
  return (
    <nav aria-label="행사 계획 단계" className="border-b border-line pb-5">
      <ol className="relative flex w-full gap-1 rounded-[10px] border border-line bg-bg p-1">
        {/* 칸 너비는 (전체 - 바깥 여백 4px×2 - 칸 사이 4px) ÷ 2 = 50% - 6px.
            오른쪽 칸으로 옮길 때는 칸 너비 + 칸 사이 4px만큼 민다. */}
        <li
          aria-hidden
          className={cn(
            'pointer-events-none absolute inset-y-1 left-1 w-[calc(50%-6px)] rounded-[8px] bg-blue-600 [view-transition-name:plan-stage-pill]',
            current === 'review' && 'translate-x-[calc(100%+4px)]',
          )}
        />
        {STAGES.map((stage, index) => {
          const active = current === stage
          // 지금 보고 있는 칸은 누를 것이 없다. 조건 쪽은 언제나 돌아갈 수 있다.
          const enabled = Boolean(eventId) && !active && (stage === 'conditions' || canReview)
          const making = stage === 'review' && generation === 'making'
          const body = (
            <span className={cn('flex items-center gap-2', LABEL_TRANSITION[stage])}>
              <span
                aria-hidden
                className={cn(
                  'grid size-[22px] shrink-0 place-items-center rounded-full text-[11px]',
                  active ? 'bg-white/20 text-white' : 'bg-blue-100 text-blue-700',
                )}
              >
                {index + 1}
              </span>
              {LABEL[stage]}
              {making && (
                <span className="flex items-center gap-[6px] text-label font-medium text-blue-700">
                  <span
                    aria-hidden
                    className="size-[5px] animate-progress-dim rounded-full bg-blue-600 motion-reduce:animate-none"
                  />
                  만드는 중
                </span>
              )}
            </span>
          )
          return (
            <li key={stage} className="flex min-w-0 flex-1">
              {enabled ? (
                <Link
                  className={cn(
                    SEGMENT,
                    'text-ink2 hover:bg-card',
                    stage === 'review' && generation === 'ready' && 'bg-blue-50 text-blue-700',
                  )}
                  to={`/planning?${new URLSearchParams({ eventId: eventId as string, stage })}`}
                  viewTransition
                >
                  {body}
                </Link>
              ) : (
                <span
                  aria-current={active ? 'page' : undefined}
                  aria-disabled={!active || undefined}
                  className={cn(
                    SEGMENT,
                    active ? 'text-white' : making ? 'text-ink2' : 'cursor-not-allowed text-mute',
                  )}
                >
                  {body}
                </span>
              )}
            </li>
          )
        })}
      </ol>
      {!canReview && !generation && current === 'conditions' && (
        <p className="mt-2 text-label text-mute">초안을 만들면 계획 검토로 넘어갈 수 있어요.</p>
      )}
    </nav>
  )
}
