// 전체 화면 상태 3종(계획 생성 중 · 참여 요청 대기 · 서버 오류)과 그 공통 틀.
// 데이터·이동은 props로 받고, 어느 라우트에 둘지는 화면 이슈에서 정한다.
import type { ReactNode } from 'react'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { ProgressBar } from '@/shared/ui/ProgressBar'
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

interface PlanGeneratingProps {
  steps: Array<{ label: string; desc?: string }>
  // 지금 하고 있는 단계 순번(0부터). 앞은 끝난 단계, 뒤는 남은 단계.
  current: number
  onCancel: () => void
}

export function PlanGeneratingScreen({ steps, current, onCancel }: PlanGeneratingProps) {
  return (
    <StateScreen
      title="계획을 만들고 있어요"
      desc="보통 20초 정도 걸려요. 창을 닫아도 계속 만들어둘게요."
    >
      <Card className="flex w-[560px] max-w-full flex-col gap-[16px] px-[26px] pt-[24px] pb-[26px]">
        <ProgressBar value={current + 1} max={steps.length} />
        {steps.map((step, i) => {
          const state = i < current ? 'done' : i === current ? 'current' : 'todo'
          return (
            <div key={step.label} className="flex items-center gap-[13px]">
              <span
                className={cn(
                  'flex size-[24px] shrink-0 items-center justify-center rounded-full font-bold',
                  state === 'done' && 'bg-blue-600 text-[11px] text-white',
                  state === 'current' && 'border-[2.5px] border-blue-600 text-[9px] text-blue-600',
                  state === 'todo' && 'bg-track',
                )}
              >
                {state === 'done' ? '✓' : state === 'current' ? '●' : null}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
                <p
                  className={cn(
                    'text-[14px]',
                    state === 'current' ? 'font-bold text-blue-700' : 'font-medium',
                    state === 'todo' ? 'text-mute' : state === 'done' && 'text-ink2',
                  )}
                >
                  {step.label}
                </p>
                {state === 'current' && step.desc && (
                  <p className="text-caption text-mute">{step.desc}</p>
                )}
              </div>
              {state === 'current' && (
                <Chip tone="approved" size="sm">
                  진행 중
                </Chip>
              )}
            </div>
          )
        })}
      </Card>
      <Button variant="secondary" size="lg" onClick={onCancel}>
        취소하고 돌아가기
      </Button>
    </StateScreen>
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
    ['대표', owner],
  ]
  return (
    <StateScreen
      title="허가를 기다리고 있어요"
      desc="대표가 허가하면 바로 쓸 수 있어요. 그 전까지는 동아리 자료와 행사를 볼 수 없어요."
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
