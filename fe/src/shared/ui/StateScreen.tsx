// 전체 화면 상태 3종(계획 생성 중 · 참여 요청 대기 · 서버 오류)과 그 공통 틀.
// 데이터·이동은 props로 받고, 어느 라우트에 둘지는 화면 이슈에서 정한다.
import { useEffect, useState, type ReactNode } from 'react'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Tori } from '@/shared/ui/Tori'

interface StateScreenProps {
  title: string
  desc: string
  children?: ReactNode
}

export function StateScreen({ title, desc, children }: StateScreenProps) {
  return (
    <div className="flex flex-col items-center gap-[24px] py-[50px]">
      <Tori size={104} />
      <div className="flex max-w-[470px] flex-col items-center gap-[9px] text-center">
        <h1 className="text-[26px] font-bold">{title}</h1>
        <p className="text-[13.5px] leading-[21px] text-mute">{desc}</p>
      </div>
      {children}
    </div>
  )
}

// 계획 생성은 AI 호출 한 번이라 중간 진행을 알 수 없다. 그래서 진행률 막대나
// 「조건 정리 → 단계 짜기」 같은 단계 표시를 두지 않는다 — 모르는 것을 그리면
// 가짜 진행이 된다(#179). 대신 경과 시간과 평균 소요, 지금 쓰는 조건을 보인다.
interface PlanGeneratingProps {
  // 「이 조건으로 만들어요」 한 줄. 예: "2026 봄 MT · 1박 2일 · 1인 45,000원"
  conditionLine: string
  // 잠정·보류·미정 표시. tentative면 눈에 띄게 둔다.
  marks?: Array<{ label: string; tentative?: boolean }>
  // 실측에 기반한 평균 소요(초). 진행률이 아니라 기다림의 눈금이다.
  averageSeconds?: number
  onCancel: () => void
}

function elapsedLabel(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export function PlanGeneratingScreen({
  conditionLine,
  marks = [],
  averageSeconds = 20,
  onCancel,
}: PlanGeneratingProps) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="flex justify-center py-[50px]">
      <Card className="flex w-[560px] max-w-full flex-col items-center gap-[18px] px-[40px] pt-[36px] pb-[34px]">
        <Tori size={76} />
        <div className="flex flex-col items-center gap-[9px] text-center">
          <h1 className="text-[22px] font-bold">계획을 만들고 있어요</h1>
          <p className="text-[13.5px] leading-[21px] text-mute">
            지금까지 정한 조건으로 준비 순서를 짜고 있어요. 보통 {averageSeconds}초쯤 걸려요.
          </p>
        </div>

        {/* 끝까지 몇 퍼센트인지 모르므로 차오르지 않는다. 살아 있다는 표시만 한다. */}
        <div className="flex gap-[6px]" aria-hidden>
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="size-[6px] animate-pulse rounded-full bg-blue-300"
              style={{ animationDelay: `${i * 0.25}s` }}
            />
          ))}
        </div>

        <p className="text-[15px] font-medium text-mute tabular-nums" aria-live="off">
          {elapsedLabel(seconds)}
        </p>

        <div className="flex w-full flex-col gap-[7px] rounded-[12px] bg-bg px-[18px] pt-[14px] pb-[15px]">
          <p className="text-label text-mute">이 조건으로 만들어요</p>
          <p className="text-[14px] font-medium text-ink">{conditionLine}</p>
          {marks.length > 0 && (
            <div className="flex flex-wrap gap-[6px] pt-[2px]">
              {marks.map((mark) => (
                <Chip key={mark.label} tone={mark.tentative ? 'approved' : 'neutral'} size="sm">
                  {mark.label}
                </Chip>
              ))}
            </div>
          )}
        </div>

        <Button variant="secondary" onClick={onCancel}>
          그만두기
        </Button>
      </Card>
    </div>
  )
}

interface JoinPendingProps {
  club?: string
  role?: string
  sentAt?: string
  owner?: string
  onCancelRequest: () => void
  onFindOther: () => void
}

export function JoinPendingScreen({
  club,
  role,
  sentAt,
  owner,
  onCancelRequest,
  onFindOther,
}: JoinPendingProps) {
  const rows = [
    ['동아리', club],
    ['내 역할', role],
    ['보낸 시각', sentAt],
    ['회장', owner],
  ]
  return (
    <StateScreen
      title="허가를 기다리고 있어요"
      desc="회장이 허가하면 바로 쓸 수 있어요. 그 전까지는 동아리 자료와 행사를 볼 수 없어요."
    >
      <Card className="flex w-[460px] max-w-full flex-col gap-[18px] px-[26px] pt-[24px] pb-[26px]">
        <div className="flex items-center justify-between">
          <h2 className="text-h3">보낸 요청</h2>
          <Chip tone="pending" size="sm">
            대기 중
          </Chip>
        </div>
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between">
            <span className="text-[12.5px] text-mute">{label}</span>
            <span className="text-[13.5px] font-bold">{value ?? '—'}</span>
          </div>
        ))}
        <p className="border-t border-line pt-[18px] text-[12px] leading-[18px] text-mute">
          허가되면 가입하신 이메일로 알려드릴게요.
        </p>
      </Card>
      <div className="flex gap-[9px]">
        <Button variant="secondary" size="lg" onClick={onCancelRequest}>
          요청 취소
        </Button>
        <Button variant="soft" size="lg" onClick={onFindOther}>
          다른 동아리 찾기
        </Button>
      </div>
    </StateScreen>
  )
}

interface ServerErrorProps {
  // 예: "SRV-500 · 3/11 09:14"
  code?: string
  offline?: boolean
  onRetry: () => void
  onHome: () => void
}

export function ServerErrorScreen({ code, offline, onRetry, onHome }: ServerErrorProps) {
  return (
    <StateScreen
      title="잠시 문제가 생겼어요"
      desc="제 잘못이에요. 잠시 뒤에 다시 눌러 주세요. 하던 작업은 저장돼 있어요."
    >
      <div className="flex gap-[9px]">
        <Button size="lg" className="text-[13px]" onClick={onRetry}>
          다시 시도
        </Button>
        <Button variant="secondary" size="lg" onClick={onHome}>
          메인으로
        </Button>
      </div>
      {code && (
        <div className="flex items-center gap-[10px] rounded-[10px] bg-chip px-[14px] py-[9px]">
          <span className="text-[11px] font-medium text-mute">오류 코드</span>
          <span className="text-caption font-bold text-ink2">{code}</span>
        </div>
      )}
      {offline && (
        <div className="flex w-[470px] max-w-full items-center gap-[11px] rounded-[12px] bg-pending-bg px-[16px] pt-[12px] pb-[13px] text-pending">
          <span className="text-[12px] font-bold">!</span>
          <div className="flex flex-col gap-[3px]">
            <p className="text-[12px] font-bold">인터넷 연결이 끊겼어요</p>
            <p className="text-caption leading-[17px]">연결이 돌아오면 자동으로 다시 불러옵니다.</p>
          </div>
        </div>
      )}
    </StateScreen>
  )
}
