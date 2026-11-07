import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'
import { useCreateMeeting } from '../hooks'
import { meetingError } from '../errors'

export interface MeetingEventOption {
  id: string
  title: string
}

export function MeetingStart({ clubId, events }: { clubId: string; events: MeetingEventOption[] }) {
  const navigate = useNavigate()
  const create = useCreateMeeting(clubId)
  const [title, setTitle] = useState('')
  const [eventId, setEventId] = useState('')
  return (
    <Card className="flex flex-col items-center px-7 pt-12 pb-8">
      <Tori size={88} />
      <h2 className="mt-6 text-[22px] font-bold">회의를 시작할까요?</h2>
      <form
        className="mt-6 flex w-full flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault()
          create.mutate(
            { title: title.trim() || '회의', eventId: eventId || null },
            {
              onSuccess: (meeting) =>
                navigate(`/meetings/${encodeURIComponent(meeting.id)}`, {
                  state: { autoStart: true },
                }),
            },
          )
        }}
      >
        <Input
          label="회의 이름"
          placeholder="예: 10월 정기 회의"
          value={title}
          maxLength={200}
          onChange={(event) => setTitle(event.target.value)}
        />
        <label className="flex w-full flex-col gap-[7px]">
          <span className="text-[11.5px] font-bold text-ink2">
            연결할 행사 <span className="ml-1 font-medium text-mute">선택</span>
          </span>
          <select
            value={eventId}
            onChange={(event) => setEventId(event.target.value)}
            className="w-full rounded-[11px] border border-soft bg-bg px-[15px] py-[12px] text-[13.5px] text-ink focus:border-blue-600 focus:bg-card"
          >
            <option value="">없음</option>
            {events.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
        <p className="rounded-[12px] border border-pending-line bg-pending-bg px-4 py-3 text-caption font-bold text-pending">
          ! 참석자에게 녹음한다고 먼저 알려 주세요. 시작하면 알린 것으로 봅니다.
        </p>
        <Button type="submit" size="lg" className="w-full" disabled={create.isPending}>
          {create.isPending ? '회의를 여는 중…' : '회의 시작하기'}
        </Button>
        {create.error && (
          <p role="alert" className="text-center text-caption text-failed">
            회의를 시작하지 못했어요. {meetingError(create.error)}
          </p>
        )}
      </form>
    </Card>
  )
}
