import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'

export function CompletedEventsCard({ count }: { count: number }) {
  return (
    <Card className="flex min-w-px flex-1 flex-col gap-[10px] rounded-[16px] p-[20px]">
      <p className="text-[12.5px] font-semibold text-[#262626]">끝난 행사</p>
      <div className="flex w-full items-center gap-[8px]">
        <p className="text-[13px] font-medium whitespace-nowrap text-[#333]">{count}건</p>
        <p className="text-[11.5px] whitespace-nowrap text-[#737373]">
          정산·회고 기록이 다음 계획의 기준이 됩니다
        </p>
        <div className="h-px flex-1" />
        {/*
          TODO: L1이 아직 이 쿼리를 읽지 않아 지금은 그냥 행사 목록으로 간다.
          `GET /events?status=COMPLETE`(명세 §2)를 붙일 때 useSearchParams로 필터를 건다.
          경로에 두지 않는 건 `events/:eventId`(L2)에 잡혀버리기 때문이다.
        */}
        <Link
          to="/events?status=COMPLETE"
          className="text-[11.5px] font-medium whitespace-nowrap text-[#6b6b6b] hover:text-[#333]"
        >
          전체 보기 ›
        </Link>
      </div>
    </Card>
  )
}
