// 목록을 받아오는 동안 들어올 자리를 미리 잡아 두는 회색 덩어리(#353).
// "불러오고 있어요" 한 줄만 두면 데이터가 왔을 때 화면이 확 늘어나 글이 밀린다.
//
// 숨 쉬는 움직임은 새로 만들지 않고 토리 대화가 쓰던 progress-dim을 그대로 쓴다.
// 읽어 주는 기기에는 들리지 않아야 해서 aria-hidden이다 — 쓰는 쪽에서 묶음 전체에
// role="status"와 "불러오고 있어요"를 적어 소리로는 그쪽이 읽히게 한다.
import { cn } from '@/shared/lib/cn'

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        'animate-progress-dim rounded-[6px] bg-track motion-reduce:animate-none',
        className,
      )}
    />
  )
}
