import type { ReactNode } from 'react'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Tori } from '@/shared/ui/Tori'

export function PreviewSections({ view }: { view: string }) {
  const extras: Record<string, ReactNode> = {
    events: (
      <Card className="p-6 sm:p-8">
        <StepHeading
          title="행사도 한곳에서 살펴봐요"
          description="지금은 준비된 행사 예시만 표시해요."
        />
        <div className="mt-6 rounded-2xl border border-line p-5">
          <Chip tone="pending" size="sm">
            준비 중 · 예시
          </Chip>
          <h2 className="mt-3 text-h2">가을 네트워킹 데이</h2>
          <p className="mt-2 text-caption leading-7 text-mute">
            10월 30일 · 캠퍼스 라운지 · 예상 참가 24명
          </p>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            {['장소 예약 확인', '참가 신청 안내', '운영 물품 준비'].map((title, i) => (
              <div key={title} className="rounded-xl bg-bg p-4 text-caption">
                <span className="text-mute">0{i + 1}</span>
                <p className="mt-2 font-bold">{title}</p>
              </div>
            ))}
          </div>
        </div>
      </Card>
    ),
    accounting: (
      <Card className="p-6 sm:p-8">
        <StepHeading
          title="운영비의 흐름을 살펴봐요"
          description="자료함에 올린 예산표와 실제 지출 내역은 따로 관리해요. 아래는 예시 지출이에요."
        />
        <div className="my-6 rounded-2xl bg-blue-50 p-5">
          <p className="text-caption text-blue-700">예시 지출 합계</p>
          <p className="mt-2 text-[28px] font-bold text-blue-900">80,000원</p>
        </div>
        {[
          { title: '행사 간식', amount: '48,000원', date: '10. 16.' },
          { title: '운영 물품', amount: '32,000원', date: '10. 15.' },
        ].map((item) => (
          <div
            key={item.title}
            className="flex justify-between gap-3 border-t border-line py-4 text-[13px]"
          >
            <div>
              <p className="font-bold">{item.title}</p>
              <p className="mt-1 text-caption text-mute">{item.date} · 예시 기록</p>
            </div>
            <span className="font-bold">{item.amount}</span>
          </div>
        ))}
      </Card>
    ),
    planning: (
      <Card className="p-6 sm:p-8">
        <StepHeading
          title="행사의 큰 틀부터 잡아요"
          description="무엇을 준비할지 함께 이야기하고, 필요한 일을 단계로 나누는 화면이에요."
        />
        <div className="mt-6 rounded-xl bg-[#F4EDE2] p-5 text-[14px] leading-7">
          새로 온 팀원들과 서로 알아갈 수 있는 행사를 준비하고 싶어요.
        </div>
        <div className="mt-5 border-l-2 border-blue-300 pl-5">
          <Tori size={32} />
          <p className="mt-3 text-[13px] leading-7 text-ink2">
            예시 계획: 가벼운 소개 → 팀별 미션 → 함께 돌아보기. 인원과 예산을 정하면 필요한 준비를
            차근차근 확인할 수 있어요.
          </p>
        </div>
      </Card>
    ),
  }

  return extras[view] ?? null
}

function StepHeading({
  number,
  title,
  description,
}: {
  number?: string
  title: string
  description: string
}) {
  return (
    <header>
      {number && <p className="mb-2 text-[11px] font-bold text-blue-600">START {number}</p>}
      <h1 className="text-[23px] font-bold leading-9 tracking-tight text-ink">{title}</h1>
      <p className="mt-2 text-[13px] leading-6 text-mute">{description}</p>
    </header>
  )
}
