// P1 우측 "임시 저장한 계획". GET /events/drafts 목록이다.
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { formatMonthDay } from '@/shared/lib/format'
import type { DraftStage, EventDraftItem } from '@/features/planning/types'

// stage는 Step 개수로 서버가 계산해 준다(0개면 CHAT, 1개 이상이면 FLOW).
const STAGE_LABEL: Record<DraftStage, string> = {
  CHAT: '1단계에서 멈춤',
  FLOW: '2단계에서 멈춤',
}

export function PlanDraftsCard({
  drafts,
  onResume,
}: {
  drafts: EventDraftItem[]
  onResume: (draftId: string) => void
}) {
  return (
    <Card className="flex w-full flex-col">
      <div className="flex w-full items-center gap-[8px] px-[22px] py-[15px]">
        <p className="text-[13px] font-semibold text-[#242424]">임시 저장한 계획</p>
        <Chip variant="subtle">{drafts.length}건</Chip>
      </div>

      {drafts.map((draft) => (
        <div
          key={draft.id}
          className="flex w-full flex-col gap-[8px] border-t border-[#ededed] px-[22px] py-[13px]"
        >
          <div className="flex w-full items-center gap-[8px]">
            <p className="text-[12.5px] font-medium text-[#333]">{draft.title}</p>
            <div className="h-px flex-1" />
            <p className="text-[10.5px] whitespace-nowrap text-[#808080]">
              {formatMonthDay(draft.savedAt)} 저장
            </p>
          </div>
          <div className="flex w-full items-center gap-[8px]">
            <p className="text-[11px] text-[#7a7a7a]">{STAGE_LABEL[draft.stage]}</p>
            <div className="h-px flex-1" />
            <button
              type="button"
              onClick={() => onResume(draft.id)}
              className="text-[11px] font-medium whitespace-nowrap text-[#666] hover:text-[#333]"
            >
              이어서 하기 ›
            </button>
          </div>
        </div>
      ))}

      <p className="border-t border-[#ededed] px-[22px] py-[13px] text-[10.5px] text-[#858585]">
        불러오면 지금 대화는 사라집니다
      </p>
    </Card>
  )
}
