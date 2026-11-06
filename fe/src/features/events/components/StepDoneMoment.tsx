// 단계 완료 순간(#370). 「단계 완료로 표시」가 서버에서 끝나면 화면 가운데에 잠깐 떠서
// 무엇이 끝났고 다음이 무엇인지, 토리가 다음 단계 글을 쓰기 시작했는지를 알린다.
// 누르는 걸 막지 않고(pointer-events 없음) 스스로 사라진다. 움직임 줄이기면 움직임 없이 같은 시간만 보인다.
import { useEffect, useRef, useState } from 'react'
import { Tori } from '@/shared/ui/Tori'

// 떠 있는 시간. 사라지는 움직임(--animate-done-out 200ms)은 이 뒤에 붙는다.
export const STEP_DONE_MS = 1700
const LEAVE_MS = 200

export interface StepDone {
  // 화면에 다시 띄울 때마다 바뀌는 값. 같은 단계를 연달아 띄워도 처음부터 다시 그린다.
  key: number
  done: { position: number; name: string }
  // 다음으로 진행 중이 된 단계. 마지막 단계였으면 없다.
  next?: { position: number; name: string }
  // 다시 불러온 목록에 토리가 쓰는 중인 다음 단계 글이 있었는지
  drafting: boolean
}

export function StepDoneMoment({ moment, onFinish }: { moment: StepDone; onFinish: () => void }) {
  const [leaving, setLeaving] = useState(false)
  // 화면이 몇 초마다 다시 그려져도(초안 재조회) 타이머가 처음부터 다시 돌지 않게 최신 함수만 기억한다
  const finishRef = useRef(onFinish)
  useEffect(() => {
    finishRef.current = onFinish
  }, [onFinish])

  useEffect(() => {
    setLeaving(false)
    const leave = window.setTimeout(() => setLeaving(true), STEP_DONE_MS)
    const finish = window.setTimeout(() => finishRef.current(), STEP_DONE_MS + LEAVE_MS)
    return () => {
      window.clearTimeout(leave)
      window.clearTimeout(finish)
    }
  }, [moment.key])

  const { done, next, drafting } = moment
  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-[24px]">
      <div
        role="status"
        className={`flex w-[320px] max-w-full flex-col items-center gap-[14px] rounded-[20px] border border-line bg-card px-[28px] pt-[26px] pb-[24px] text-center shadow-[0_12px_36px_rgba(0,0,0,0.16)] motion-reduce:animate-none ${leaving ? 'animate-done-out' : 'animate-done-in'}`}
      >
        <svg aria-hidden viewBox="0 0 56 56" className="size-[56px]">
          <circle cx="28" cy="28" r="28" className="fill-done-bg" />
          <path
            d="M17.5 28.5 24.5 35.5 38.5 21"
            pathLength={1}
            strokeDasharray="1"
            fill="none"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="animate-done-draw stroke-done motion-reduce:animate-none"
          />
        </svg>
        <div className="flex flex-col gap-[5px]">
          <p className="text-[17px] leading-[24px] font-bold text-balance">
            {done.position}. {done.name} 완료
          </p>
          <p className="text-[12.5px] leading-[19px] text-ink2">
            {/* 단계 이름 뒤 조사(을/를)가 이름마다 달라 조사 없이 쓴다 */}
            {next ? `이제 ${next.position}. ${next.name} 단계예요` : '모든 단계를 마쳤어요'}
          </p>
        </div>
        {drafting && (
          <p className="flex items-center gap-[8px] rounded-[11px] bg-blue-50 px-[12px] py-[8px] text-[12px] leading-[17px] font-medium text-blue-700">
            <Tori size={22} />
            토리가 다음 단계 글을 쓰기 시작했어요
          </p>
        )}
      </div>
    </div>
  )
}
