// 공통 컴포넌트 확인용 페이지(/dev/ui). 화면이 없어 띄울 곳 없는 모달·토스트·상태 화면을 여기서 본다.
import { useState, type ReactNode } from 'react'
import { toast } from '@/shared/lib/toast'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Input, Textarea } from '@/shared/ui/Input'
import { Modal } from '@/shared/ui/Modal'
import { JoinPendingScreen, PlanGeneratingScreen, ServerErrorScreen } from '@/shared/ui/StateScreen'
import { Switch } from '@/shared/ui/Switch'
import { ToastView } from '@/shared/ui/Toast'
import { ToriNote } from '@/shared/ui/ToriNote'

const noop = () => {}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-[12px]">
      <h2 className="text-h2">{title}</h2>
      {children}
    </section>
  )
}

export default function DevUiPage() {
  const [modal, setModal] = useState<'edit' | 'cancel' | null>(null)
  const [text, setText] = useState('안녕하세요. 봄 MT 참가 신청이 3월 12일에 마감됩니다.')
  const [agree, setAgree] = useState(false)
  const [on, setOn] = useState(true)

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-[40px]">
      <h1 className="text-h1">공통 컴포넌트</h1>

      <Section title="버튼 · 칩 · 토글">
        <div className="flex flex-wrap items-center gap-[8px]">
          <Button>저장</Button>
          <Button variant="soft">다른 동아리 찾기</Button>
          <Button variant="secondary">취소</Button>
          <Button variant="danger">행사 취소하기</Button>
          <Button variant="ghost">더보기</Button>
          <Button size="sm">승인</Button>
          <Button size="sm" variant="secondary">
            미루기
          </Button>
          <Switch checked={on} onChange={setOn} label="알림" />
        </div>
        <div className="flex flex-wrap gap-[8px]">
          <Chip>공지</Chip>
          <Chip tone="done">완료</Chip>
          <Chip tone="pending">대기</Chip>
          <Chip tone="approved">실행 대기</Chip>
          <Chip tone="failed">실패·거절</Chip>
          <Chip tone="blush">블러시</Chip>
          <Chip tone="approved" size="sm">
            진행 중
          </Chip>
        </div>
      </Section>

      <Section title="입력 · 토리 안내 박스">
        <Card className="flex max-w-[660px] flex-col gap-[15px] p-[28px]">
          <div className="flex gap-[10px]">
            <Input label="시작일" type="date" defaultValue="2026-03-10" />
            <Input label="마감일" type="date" defaultValue="2026-03-12" />
          </div>
          <Input placeholder="계약서 2조에 적혀 있어요" />
          <Textarea
            label="보낼 문구"
            maxLength={500}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <ToriNote title="이름은 보낼 때 채워져요">
            문구에 {'{이름}'}을 넣으면 받는 분 이름으로 바뀌어요.
          </ToriNote>
          <ToriNote tone="cream" title="고치면 다시 검토해 주세요">
            문구가 바뀌면 승인이 풀리고 검토 대기로 돌아가요.
          </ToriNote>
          <ToriNote tone="blush" title="되돌릴 수 없어요" />
        </Card>
      </Section>

      <Section title="모달">
        <div className="flex gap-[8px]">
          <Button variant="secondary" onClick={() => setModal('edit')}>
            문구 수정 열기
          </Button>
          <Button variant="secondary" onClick={() => setModal('cancel')}>
            행사 취소 확인 열기
          </Button>
        </div>
        <Modal
          open={modal === 'edit'}
          onClose={() => setModal(null)}
          title="문구 수정"
          chip={<Chip>공지</Chip>}
          subtitle="미응답 회원 9명에게 신청 마감 안내"
          width={660}
          footer={
            <>
              <Button variant="secondary" onClick={() => setModal(null)}>
                취소
              </Button>
              <Button onClick={() => setModal(null)}>저장하고 다시 검토</Button>
            </>
          }
        >
          <Textarea
            label="보낼 문구"
            maxLength={500}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <ToriNote title="이름은 보낼 때 채워져요">
            문구에 {'{이름}'}을 넣으면 받는 분 이름으로 바뀌어요. 지금 대상은 9명이에요.
          </ToriNote>
        </Modal>
        <Modal
          open={modal === 'cancel'}
          onClose={() => setModal(null)}
          title="행사를 취소할까요?"
          chip={<Chip tone="failed">되돌릴 수 없음</Chip>}
          subtitle="2026 봄 MT · 3/21 – 3/22 · 참가 32명"
          width={600}
          footer={
            <>
              <Button variant="secondary" onClick={() => setModal(null)}>
                돌아가기
              </Button>
              <Button variant="danger" disabled={!agree} onClick={() => setModal(null)}>
                행사 취소하기
              </Button>
            </>
          }
        >
          <ToriNote title="기록은 남겨둘게요">
            지금까지의 단계와 승인 기록은 지우지 않아요.
          </ToriNote>
          <label className="flex items-center gap-[10px] text-[12.5px] font-medium text-ink2">
            <input
              type="checkbox"
              checked={agree}
              onChange={(e) => setAgree(e.target.checked)}
              className="size-[18px] accent-blue-600"
            />
            위 내용을 확인했습니다
          </label>
        </Modal>
      </Section>

      <Section title="토스트">
        <div className="grid grid-cols-2 gap-[12px]">
          <ToastView
            kind="done"
            title="승인했어요"
            desc="미납자 4명 안내 · 박수겸 이름으로 기록됨"
            action={{ label: '보기', onClick: noop }}
          />
          <ToastView kind="done" title="계획을 저장했어요" desc="3월 11일 09:14" />
          <ToastView kind="progress" title="보내는 중이에요" desc="잠시만요" />
          <ToastView
            kind="error"
            title="처리하지 못했어요"
            desc="연결이 끊겼어요. 다시 눌러 주세요"
            action={{ label: '다시 시도', onClick: noop }}
          />
        </div>
        <div>
          <Button
            variant="secondary"
            onClick={() => {
              const id = toast.show({
                kind: 'progress',
                title: '보내는 중이에요',
                desc: '잠시만요',
              })
              setTimeout(() => toast.show({ id, kind: 'done', title: '승인했어요' }), 1500)
            }}
          >
            처리 중 → 승인 완료 띄우기
          </Button>
        </div>
      </Section>

      <Section title="상태 화면">
        <Card>
          <PlanGeneratingScreen
            current={0}
            steps={[
              { label: '과거 기록 확인', desc: '올린 자료가 있으면 먼저 봅니다' },
              { label: '단계 고르기' },
              { label: '일정 계산' },
              { label: '수금·공지 정리' },
            ]}
            onCancel={noop}
          />
        </Card>
        <Card>
          <JoinPendingScreen onCancelRequest={noop} onFindOther={noop} />
        </Card>
        <Card>
          <ServerErrorScreen code="SRV-000 · 날짜 시각" offline onRetry={noop} onHome={noop} />
        </Card>
      </Section>
    </div>
  )
}
