import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { useRecordUploads } from '@/features/records/hooks'
import { recordErrorMessage, recordStatus } from '@/features/records/presentation'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { RecordsPanel } from './RecordsPanel'

export function MeetingRecordsSummary({ clubId }: { clubId: string }) {
  const [open, setOpen] = useState(false)
  const [opened, setOpened] = useState(false)
  const id = useId()
  const { records } = useRecordUploads(clubId, 1)
  return (
    <section className="space-y-3">
      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-h2">회의 자료</h2>
            <p className="mt-1 text-caption text-mute">선택한 팀 전체의 자료와 검색 준비 상태예요.</p>
          </div>
          <Link to="/records" className="text-caption text-blue-700 underline">전체 자료함</Link>
        </div>
        {records.isPending && <p role="status" className="text-caption">자료를 불러오고 있어요.</p>}
        {records.isError && (
          <p role="alert" className="text-caption text-failed">
            {recordErrorMessage(records.error)}{' '}
            <button type="button" className="underline" onClick={() => void records.refetch()}>다시 시도</button>
          </p>
        )}
        {records.isSuccess && (
          <div className="space-y-2 text-caption">
            <p>{records.data.meta ? `팀 자료 ${records.data.meta.totalCount}건` : '팀 자료 전체 개수를 확인하지 못했어요.'}</p>
            {records.data.data.length === 0 ? <p className="text-mute">아직 올린 자료가 없어요.</p> : (
              <ul className="space-y-1">
                {records.data.data.slice(0, 2).map((record) => (
                  <li key={record.id} className="break-words text-ink2">
                    {record.fileName} · {record.indexError ? '검색 준비 실패' : recordStatus(record).label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        <Button variant="secondary" size="sm" aria-expanded={open} aria-controls={id} onClick={() => {
          setOpened(true)
          setOpen((value) => !value)
        }}>
          {open ? '접기' : '자세히 보기'}
        </Button>
      </Card>
      <div id={id} hidden={!open}>{opened && <RecordsPanel clubId={clubId} />}</div>
    </section>
  )
}
