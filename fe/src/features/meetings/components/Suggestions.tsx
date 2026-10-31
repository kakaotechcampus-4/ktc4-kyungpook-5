import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Input, Textarea } from '@/shared/ui/Input'
import { MEMBER_ROLE_LABEL } from '@/shared/lib/labels'
import { meetingsApi } from '../api'
import {
  confirmedApi,
  displayTime,
  seoulInput,
  seoulIso,
  type ConfirmedFields,
  type ConfirmedTask,
  type Recipient,
} from '../confirmed'
import { meetingError } from '../errors'
import type { Suggestion } from '../types'

const statusLabels: Record<ConfirmedTask['reminder']['status'], string> = {
  PENDING: '예약 대기',
  SENDING: '서버 발송 중',
  SERVICE_ACCEPTED: 'Push 서비스 접수',
  FAILED: '발송 실패',
  CANCELLED: '예약 취소',
}
function ReviewFields({
  clubId,
  suggestion,
  existing,
  onSaved,
}: {
  clubId: string
  suggestion: Suggestion
  existing?: ConfirmedTask
  onSaved: () => void
}) {
  const memoHelpId = useId()
  const [kind, setKind] = useState<'TASK' | 'SCHEDULE'>(
    existing?.kind ?? (suggestion.kind === 'SCHEDULE' ? 'SCHEDULE' : 'TASK'),
  )
  const [title, setTitle] = useState(existing?.title ?? suggestion.title)
  const [description, setDescription] = useState(
    existing ? (existing.description ?? '') : (suggestion.description ?? ''),
  )
  const [assignee, setAssignee] = useState(
    existing?.assigneeName ?? suggestion.suggestedAssignee ?? '',
  )
  const [assigneeAccount, setAssigneeAccount] = useState(existing?.assigneeAccountId ?? '')
  const [date, setDate] = useState(suggestion.dueDate ?? '')
  const [itemAt, setItemAt] = useState(
    seoulInput(
      existing?.dueAt ??
        existing?.scheduledAt ??
        suggestion.dueAt ??
        suggestion.scheduledAt ??
        null,
    ),
  )
  const [reminderAt, setReminderAt] = useState(seoulInput(existing?.reminder.reminderAt ?? null))
  const [selected, setSelected] = useState<string[]>(existing?.reminder.recipientAccountIds ?? [])
  const [checked, setChecked] = useState(false)
  const [notice, setNotice] = useState('')
  const client = useQueryClient()
  const recipients = useQuery({
    queryKey: ['recipients', clubId],
    queryFn: () => confirmedApi.recipients(clubId),
  })
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ['suggestions', clubId] })
    await client.invalidateQueries({ queryKey: ['confirmed', clubId] })
    onSaved()
  }
  const draft = useMutation({
    mutationFn: () =>
      meetingsApi.patchSuggestion(clubId, suggestion, {
        title: title.trim(),
        description,
        dueDate: date || null,
        suggestedAssignee: assignee.trim() || null,
      }),
    onSuccess: async () => {
      setNotice('후보 수정만 저장했습니다. 일정·알림 예약은 생성되지 않았습니다.')
      await refresh()
    },
  })
  const save = useMutation({
    mutationFn: (fields: ConfirmedFields) =>
      existing
        ? confirmedApi.update(clubId, existing, fields)
        : confirmedApi.confirm(clubId, suggestion.id, suggestion.version, fields),
    onSuccess: async () => {
      setNotice(
        '내용과 지정 수신자를 저장하고 서버 예약을 생성했습니다. 기기 수신은 별도로 확인해 주세요.',
      )
      setChecked(false)
      await refresh()
    },
  })
  const busy = save.isPending || draft.isPending
  const invalidate = () => {
    setChecked(false)
    setNotice('')
  }
  const unavailableAssignee =
    recipients.isSuccess &&
    Boolean(
      assigneeAccount &&
      !recipients.data.some((recipient) => recipient.accountId === assigneeAccount),
    )
  const unavailableRecipients = recipients.isSuccess
    ? selected.filter((id) => !recipients.data.some((recipient) => recipient.accountId === id))
    : []
  const future = reminderAt && new Date(`${reminderAt}:00+09:00`).getTime() > Date.now()
  const valid =
    title.trim() &&
    assignee.trim() &&
    itemAt &&
    reminderAt &&
    selected.length > 0 &&
    future &&
    reminderAt <= itemAt &&
    !recipients.isError &&
    !unavailableAssignee &&
    selected.every((id) => recipients.data?.some((r) => r.accountId === id))
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (!valid || !checked) return
        save.mutate({
          assigneeName: assignee.trim(),
          assigneeAccountId: assigneeAccount || null,
          kind,
          title: title.trim(),
          description: description || null,
          dueAt: kind === 'TASK' ? seoulIso(itemAt) : null,
          scheduledAt: kind === 'SCHEDULE' ? seoulIso(itemAt) : null,
          timezone: 'Asia/Seoul',
          reminderAt: seoulIso(reminderAt),
          recipientAccountIds: selected,
        })
      }}
    >
      <Input
        label="내용"
        value={title}
        maxLength={200}
        required
        onChange={(e) => {
          setTitle(e.target.value)
          invalidate()
        }}
      />
      <Input
        label="담당자 이름"
        value={assignee}
        required
        onChange={(e) => {
          setAssignee(e.target.value)
          invalidate()
        }}
      />
      <label className="block text-caption font-bold">
        담당 계정 (선택)
        <select
          className="mt-2 w-full rounded-lg border border-soft bg-bg p-3"
          value={assigneeAccount}
          onChange={(e) => {
            const id = e.target.value
            setAssigneeAccount(id)
            if (id) setAssignee(recipients.data?.find((r) => r.accountId === id)?.name ?? assignee)
            invalidate()
          }}
        >
          <option value="">이름으로 확인 · 계정 미연결</option>
          {unavailableAssignee && (
            <option value={assigneeAccount} disabled>
              이전 담당 계정 · 다시 선택 필요
            </option>
          )}
          {recipients.data?.map((r) => (
            <option key={r.accountId} value={r.accountId}>
              {r.name} · {MEMBER_ROLE_LABEL[r.role]}
            </option>
          ))}
        </select>
      </label>
      {unavailableAssignee && (
        <p role="alert" className="text-caption text-failed">
          이전 담당 계정은 현재 이용 대상이 아니에요. 회장·임원 계정을 선택하거나 이름으로 확인해
          주세요.
        </p>
      )}
      <Textarea
        label="기타 메모 (선택)"
        value={description}
        placeholder="준비물, 참고 링크, 전달할 내용을 자유롭게 적어 주세요."
        rows={4}
        maxLength={10000}
        aria-describedby={memoHelpId}
        onChange={(e) => {
          setDescription(e.target.value)
          invalidate()
        }}
      />
      <p id={memoHelpId} className="text-caption text-mute">
        여러 줄로 적을 수 있어요. 비워 두어도 저장할 수 있고, 저장 후에도 다시 확인·수정할 수
        있어요.
      </p>
      {!existing && (
        <details className="rounded-lg border border-line p-3 text-caption">
          <summary>추출 후보만 수정</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Input
              label="후보 날짜 (정확한 시각 아님)"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>
          <Button
            className="mt-3"
            variant="secondary"
            disabled={busy || !title.trim()}
            onClick={() => draft.mutate()}
          >
            후보만 저장
          </Button>
        </details>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-caption font-bold">
          항목 종류
          <select
            className="mt-2 w-full rounded-lg border border-soft bg-bg p-3"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as 'TASK' | 'SCHEDULE')
              invalidate()
            }}
          >
            <option value="TASK">할 일</option>
            <option value="SCHEDULE">일정</option>
          </select>
        </label>
        <Input
          label={kind === 'TASK' ? '마감 시각 · 한국시간' : '일정 시각 · 한국시간'}
          type="datetime-local"
          required
          value={itemAt}
          onChange={(e) => {
            setItemAt(e.target.value)
            invalidate()
          }}
        />
      </div>
      <Input
        label="알림 시각 · 한국시간 (Asia/Seoul)"
        type="datetime-local"
        required
        value={reminderAt}
        onChange={(e) => {
          setReminderAt(e.target.value)
          invalidate()
        }}
      />
      <fieldset className="rounded-xl border border-soft p-3">
        <legend className="px-2 text-caption font-bold">알림 수신 계정</legend>
        <p className="mb-2 text-caption text-mute">
          담당자와 별도로 선택한 소속 회장·임원 계정에만 알립니다. 추출된 이름을 계정으로 자동
          확정하지 않습니다.
        </p>
        {recipients.isPending && <p>회장·임원 계정 확인 중…</p>}
        {recipients.isError && (
          <div role="alert">
            <p className="text-failed">
              수신 계정 목록을 확인하지 못했습니다. {meetingError(recipients.error)}
            </p>
            <Button variant="secondary" onClick={() => void recipients.refetch()}>
              다시 확인
            </Button>
          </div>
        )}
        {recipients.data?.map((r: Recipient) => (
          <label key={r.accountId} className="mb-2 flex items-center gap-2">
            <input
              type="checkbox"
              checked={selected.includes(r.accountId)}
              onChange={(e) => {
                setSelected((old) =>
                  e.target.checked ? [...old, r.accountId] : old.filter((id) => id !== r.accountId),
                )
                invalidate()
              }}
            />
            {r.name} · {MEMBER_ROLE_LABEL[r.role]}
          </label>
        ))}
        {recipients.data?.length === 0 && <p>선택할 회장·임원 계정이 없습니다.</p>}
        {unavailableRecipients.length > 0 && (
          <div role="alert" className="space-y-2 text-caption text-failed">
            <p>
              이전 수신 계정 {unavailableRecipients.length}개는 현재 이용 대상이 아니에요. 제외한 뒤
              수신자를 다시 확인해 주세요.
            </p>
            <Button
              variant="secondary"
              onClick={() => {
                setSelected((ids) => ids.filter((id) => !unavailableRecipients.includes(id)))
                invalidate()
              }}
            >
              이용할 수 없는 수신 계정 제외
            </Button>
          </div>
        )}
      </fieldset>
      <div className="rounded-xl bg-bg p-4 text-caption leading-6">
        <p>
          <strong>{title || '내용 미입력'}</strong> · {kind === 'TASK' ? '할 일' : '일정'}
        </p>
        <p>
          {kind === 'TASK' ? '마감' : '일정'}: {itemAt.replace('T', ' ') || '미정'} / 알림:{' '}
          {reminderAt.replace('T', ' ') || '미정'} (한국시간)
        </p>
        <p>
          담당: {assignee || '미정'}
          {assigneeAccount ? ' · 계정 연결' : ' · 이름 확인'}
        </p>
        <p>
          수신:{' '}
          {selected
            .map((id) => recipients.data?.find((r) => r.accountId === id)?.name ?? '확인 필요')
            .join(', ') || '미지정'}
        </p>
        {description.trim() && (
          <div className="mt-2">
            <p className="font-bold">기타 메모</p>
            <p className="whitespace-pre-wrap break-words">{description}</p>
          </div>
        )}
        <label className="mt-2 flex items-center gap-2">
          <input
            type="checkbox"
            checked={checked}
            disabled={!valid}
            onChange={(e) => setChecked(e.target.checked)}
          />
          내용·시각·담당/수신자를 확인했습니다.
        </label>
      </div>
      {!!reminderAt && !future && (
        <p className="text-caption text-failed">알림은 미래 시각으로 지정해 주세요.</p>
      )}
      {reminderAt && itemAt && reminderAt > itemAt && (
        <p className="text-caption text-failed">알림 시각은 일정·마감 이후가 될 수 없습니다.</p>
      )}
      {(save.error || draft.error) && (
        <p role="alert" className="text-failed">
          {meetingError(save.error || draft.error)}
        </p>
      )}
      {notice && (
        <p role="status" className="text-blue-700">
          {notice}
        </p>
      )}
      <Button type="submit" disabled={!valid || !checked || busy}>
        {busy ? '서버 확인 중…' : existing ? '확인한 내용으로 예약 변경' : '확인 후 저장·예약'}
      </Button>
    </form>
  )
}
export function Suggestions({
  clubId,
  suggestions,
  onSaved,
}: {
  clubId: string
  suggestions: Suggestion[]
  onSaved: () => void
}) {
  const confirmed = useQuery({
    queryKey: ['confirmed', clubId],
    queryFn: () => confirmedApi.list(clubId),
  })
  return (
    <section className="space-y-4" aria-label="일정·할 일 후보">
      <h2 className="text-h2">확인할 일정·할 일</h2>
      <p className="text-caption text-ink2">
        내용과 시각, 실제 수신 계정을 확인한 뒤 저장·예약합니다.
      </p>
      {!suggestions.length && (
        <Card className="p-5 text-mute">
          아직 확인할 후보가 없습니다. 자료 조회 결과와 별도로 표시됩니다.
        </Card>
      )}
      {suggestions.map((s) => (
        <Card key={`${s.id}:${s.version}`} className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-h3">{s.title}</h3>
            <Chip>{s.status === 'ACCEPTED' ? '수락 기록' : '검토 후보'}</Chip>
          </div>
          {confirmed.data?.some((item) => item.suggestionId === s.id) ? (
            <p className="text-ink2">
              확정 항목이 저장됐습니다. 아래에서 실제 예약 상태와 변경·취소를 확인해 주세요.
            </p>
          ) : (
            <ReviewFields clubId={clubId} suggestion={s} onSaved={onSaved} />
          )}
        </Card>
      ))}
    </section>
  )
}
export function ConfirmedTasks({
  clubId,
  highlightTaskId,
}: {
  clubId: string
  highlightTaskId?: string
}) {
  const client = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const items = useQuery({
    queryKey: ['confirmed', clubId],
    queryFn: () => confirmedApi.list(clubId),
    refetchInterval: 10000,
  })
  const linked = useQuery({
    queryKey: ['confirmed-detail', clubId, highlightTaskId],
    queryFn: () => confirmedApi.get(clubId, highlightTaskId!),
    enabled: !!highlightTaskId,
  })
  const cancel = useMutation({
    mutationFn: (item: ConfirmedTask) => confirmedApi.cancel(clubId, item),
    onSuccess: () => client.invalidateQueries({ queryKey: ['confirmed', clubId] }),
  })
  const list = [...(items.data ?? [])]
  if (linked.data && !list.some((item) => item.id === linked.data.id)) list.unshift(linked.data)
  return (
    <section className="space-y-3" aria-label="팀 확정 항목">
      <h2 className="text-h2">저장한 일정·알림 예약</h2>
      {items.isError && (
        <p role="alert" className="text-failed">
          확정 항목 조회 실패 · {meetingError(items.error)}
        </p>
      )}
      {linked.isError && (
        <p role="alert" className="text-failed">
          알림의 항목을 열지 못했습니다. 소속을 확인해 주세요.
        </p>
      )}
      {cancel.isError && (
        <p role="alert" className="text-failed">
          {meetingError(cancel.error)}
        </p>
      )}
      {!items.isPending && !items.isError && !list.length && (
        <p className="text-mute">이 팀에 저장한 항목이 없습니다.</p>
      )}
      {list.map((item) => (
        <Card
          key={`${item.id}:${item.version}`}
          id={`task-${item.id}`}
          className={`p-5 ${highlightTaskId === item.id ? 'border-blue-600' : ''}`}
        >
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-h3">{item.title}</h3>
            <Chip tone={item.reminder.status === 'FAILED' ? 'failed' : 'neutral'}>
              {statusLabels[item.reminder.status]}
            </Chip>
          </div>
          <p className="mt-2">
            {item.kind === 'TASK' ? '마감' : '일정'}: {displayTime(item.dueAt ?? item.scheduledAt)}
          </p>
          <p className="mt-1 text-caption">담당: {item.assigneeName || '미지정'}</p>
          {item.description?.trim() && (
            <div className="mt-3 text-caption">
              <p className="font-bold">기타 메모</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-ink2">{item.description}</p>
            </div>
          )}
          <p className="mt-1 text-caption">
            알림: {displayTime(item.reminder.reminderAt)} · 지정 수신자{' '}
            {item.reminder.recipientAccountIds.length}명
          </p>
          {item.reminder.status === 'SERVICE_ACCEPTED' && (
            <p className="mt-2 text-caption text-mute">
              Push 서비스가 {item.reminder.acceptedCount}건을 접수했습니다. 실제 기기 표시는 수신
              기기에서 확인해 주세요.
            </p>
          )}
          {item.reminder.status === 'FAILED' && (
            <p className="mt-2 text-caption text-failed">
              서버 발송 실패. 구독 상태를 확인하고 미래 시각으로 예약을 변경해 주세요.
            </p>
          )}
          {item.status === 'ACTIVE' && (
            <div className="mt-3 flex gap-2">
              <Button
                variant="secondary"
                onClick={() => setEditing(editing === item.id ? null : item.id)}
              >
                내용·예약 변경
              </Button>
              <Button
                variant="secondary"
                disabled={cancel.isPending}
                onClick={() => cancel.mutate(item)}
              >
                예약 취소
              </Button>
            </div>
          )}
          {editing === item.id && item.status === 'ACTIVE' && (
            <div className="mt-5 border-t border-line pt-5">
              <ReviewFields
                clubId={clubId}
                existing={item}
                suggestion={
                  {
                    id: item.suggestionId,
                    title: item.title,
                    description: item.description,
                    suggestedAssignee: item.assigneeName ?? null,
                    dueDate: null,
                  } as Suggestion
                }
                onSaved={() => setEditing(null)}
              />
            </div>
          )}
        </Card>
      ))}
    </section>
  )
}
