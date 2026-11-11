import type { ReactNode } from 'react'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { Modal } from '@/shared/ui/Modal'
import { Tori } from '@/shared/ui/Tori'

function Consequences({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-[12px] bg-failed-bg px-4 py-3.5 text-failed">
      <p className="text-caption font-bold">{title}</p>
      <ul className="mt-1.5 space-y-1 text-caption">
        {items.map((item) => (
          <li key={item}>· {item}</li>
        ))}
      </ul>
    </div>
  )
}

function ToriNote({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3 rounded-[12px] border border-blue-200 bg-blue-50 px-4 py-3.5 text-blue-700">
      <Tori size={36} />
      <div className="text-caption">
        <p className="font-bold">{title}</p>
        <p className="mt-0.5">{children}</p>
      </div>
    </div>
  )
}

export function EndMeetingModal({
  open,
  subtitle,
  heard,
  answered,
  recording,
  busy,
  onClose,
  onConfirm,
}: {
  open: boolean
  subtitle: string
  heard: number
  answered: number
  recording: boolean
  busy: boolean
  onClose: () => void
  onConfirm: () => void
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="회의를 끝낼까요?"
      chip={<Chip tone="failed">되돌릴 수 없음</Chip>}
      subtitle={subtitle}
      width={600}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {recording ? '계속 녹음' : '취소'}
          </Button>
          <Button variant="danger" disabled={busy} onClick={onConfirm}>
            회의 끝내기
          </Button>
        </>
      }
    >
      <Consequences
        title="끝내면 이렇게 됩니다"
        items={[
          '녹음이 멈추고, 이 회의에 이어서 녹음할 수 없어요',
          '끝낸 뒤에 한 말은 기록되지 않아요',
          '다시 녹음하려면 새 회의를 시작해야 해요',
        ]}
      />
      <ToriNote title="들은 말과 토리 답은 남아요">
        지금까지 들은 말 {heard}개와 토리가 찾은 답 {answered}개는 지우지 않아요.
      </ToriNote>
    </Modal>
  )
}

export function LeaveMeetingModal({
  open,
  subtitle,
  onStay,
  onLeave,
}: {
  open: boolean
  subtitle: string
  onStay: () => void
  onLeave: () => void
}) {
  return (
    <Modal
      open={open}
      onClose={onStay}
      title="녹음을 멈추고 나갈까요?"
      chip={<Chip tone="failed">녹음 중</Chip>}
      subtitle={subtitle}
      width={600}
      footer={
        <>
          <Button variant="secondary" onClick={onStay}>
            머무르기
          </Button>
          <Button variant="danger" onClick={onLeave}>
            녹음 멈추고 나가기
          </Button>
        </>
      }
    >
      <Consequences
        title="다른 화면으로 가면 녹음이 멈춰요"
        items={[
          '나가 있는 동안 한 말은 기록되지 않아요',
          '회의는 끝나지 않고 ‘진행 중’으로 남아요',
          '이 회의는 다시 녹음할 수 없어요. 계속하려면 새 회의를 시작해야 해요',
        ]}
      />
      <ToriNote title="잠깐 다른 화면을 봐야 한다면">
        메뉴를 새 탭으로 열면 녹음을 멈추지 않고 볼 수 있어요.
      </ToriNote>
    </Modal>
  )
}
