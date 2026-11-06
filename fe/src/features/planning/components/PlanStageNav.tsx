// 행사 조건 ↔ 계획 검토를 오가는 두 칸 토글.
//
// 전에는 "① 행사 조건 → ② 계획 검토"라고 적힌 안내문이었고, 오가는 길은 화면마다
// 흩어진 작은 글자 링크(「기존 초안 검토하기」·「행사 조건 수정」)였다. 두 화면을
// 오가는 것이 이 기능의 주된 움직임이라, 안내문 자리를 그대로 이동 수단으로 바꿨다.
//
// 대화창과 같은 너비로 두고, 지금 보고 있는 쪽을 색으로 채운다.
import { Link } from 'react-router-dom'
import { cn } from '@/shared/lib/cn'

type Stage = 'conditions' | 'review'

const LABEL: Record<Stage, string> = { conditions: '행사 조건', review: '계획 검토' }
const STAGES: Stage[] = ['conditions', 'review']

const SEGMENT =
  'flex min-h-11 flex-1 items-center justify-center gap-2 rounded-[8px] px-3 text-[13.5px] font-bold transition-colors duration-150 motion-reduce:transition-none'

export function PlanStageNav({
  current,
  eventId,
  // 초안이 없으면 계획 검토에 볼 것이 없다. 눌러도 되돌아오므로 아예 잠근다.
  canReview = false,
}: {
  current: Stage
  eventId?: string | null
  canReview?: boolean
}) {
  return (
    <nav aria-label="행사 계획 단계" className="border-b border-line pb-5">
      <ol className="flex w-full gap-1 rounded-[10px] border border-line bg-bg p-1">
        {STAGES.map((stage, index) => {
          const active = current === stage
          // 지금 보고 있는 칸은 누를 것이 없다. 조건 쪽은 언제나 돌아갈 수 있다.
          const enabled = Boolean(eventId) && !active && (stage === 'conditions' || canReview)
          const body = (
            <>
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
            </>
          )
          return (
            <li key={stage} className="flex min-w-0 flex-1">
              {enabled ? (
                <Link
                  className={cn(SEGMENT, 'text-ink2 hover:bg-card')}
                  to={`/planning?${new URLSearchParams({ eventId: eventId as string, stage })}`}
                >
                  {body}
                </Link>
              ) : (
                <span
                  aria-current={active ? 'page' : undefined}
                  aria-disabled={!active || undefined}
                  className={cn(
                    SEGMENT,
                    active ? 'bg-blue-600 text-white' : 'cursor-not-allowed text-mute',
                  )}
                >
                  {body}
                </span>
              )}
            </li>
          )
        })}
      </ol>
      {!canReview && current === 'conditions' && (
        <p className="mt-2 text-label text-mute">초안을 만들면 계획 검토로 넘어갈 수 있어요.</p>
      )}
    </nav>
  )
}
