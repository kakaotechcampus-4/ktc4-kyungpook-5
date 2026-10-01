import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import type { EventDraft } from '@/features/events/types'

export function DraftEventsCard({ drafts }: { drafts: EventDraft[] }) {
  return (
    <Card className="flex min-w-px flex-1 flex-col gap-[10px] rounded-[16px] p-[20px]">
      <p className="text-[12.5px] font-semibold text-[#262626]">계획 중</p>
      {drafts.length === 0 ? (
        <p className="text-[11.5px] text-[#737373]">아직 계획 중인 행사가 없습니다.</p>
      ) : (
        drafts.map((draft) => (
          <div key={draft.id} className="flex w-full items-center gap-[8px]">
            <p className="text-[13px] font-medium whitespace-nowrap text-[#333]">{draft.title}</p>
            <Chip variant="subtle">{draft.stageLabel}</Chip>
            <div className="h-px flex-1" />
            <Link
              to={`/planning/${draft.id}`}
              className="text-[11.5px] font-medium whitespace-nowrap text-[#6b6b6b] hover:text-[#333]"
            >
              이어서 하기 ›
            </Link>
          </div>
        ))
      )}
    </Card>
  )
}
