import { useState, type FormEvent } from 'react'
import { useRecordDetail, useRecordUploads, useRetryRecordIndex } from '@/features/records/hooks'
import {
  formatFileSize,
  parseErrorMessage,
  RECORD_CATEGORIES,
  recordErrorMessage,
  RECORD_STATUS,
} from '@/features/records/presentation'
import type { ClubRecord, RecordCategory } from '@/features/records/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Input } from '@/shared/ui/Input'

function RecordStatusRow({ clubId, record }: { clubId: string; record: ClubRecord }) {
  const detail = useRecordDetail(clubId, record.id)
  const retryIndex = useRetryRecordIndex(clubId, record.id)
  const current = detail.data ?? record
  const status = RECORD_STATUS[current.parseStatus]

  return (
    <li className="flex flex-col gap-[9px] border-t border-line py-[16px] first:border-0">
      <div className="flex flex-wrap items-center justify-between gap-[10px]">
        <span className="min-w-0 flex-1 break-words text-[13px] font-bold text-ink">
          {current.fileName}
        </span>
        <Chip size="sm" tone={status.tone}>
          {status.label}
        </Chip>
      </div>
      <p className="text-[11px] text-mute">
        {current.fileType} · {formatFileSize(current.size)} ·{' '}
        {RECORD_CATEGORIES.find((category) => category.value === current.category)?.label}
      </p>
      <p className="text-[12px] leading-[19px] text-ink2">
        {current.parseStatus === 'FAILED'
          ? parseErrorMessage(detail.data?.parseError ?? null)
          : current.indexError
            ? '파일 내용은 읽었지만 검색 준비에 실패했어요. 서버 설정을 확인하거나 다시 시도해 주세요.'
            : status.description}
      </p>
      {detail.isError && (
        <p role="alert" className="text-[12px] text-failed">
          {recordErrorMessage(detail.error)} 마지막으로 받은 상태를 표시하고 있어요.
        </p>
      )}
      {retryIndex.isError && (
        <p role="alert" className="text-[12px] text-failed">
          {recordErrorMessage(retryIndex.error)} 검색 준비 재시도가 완료되지 않았어요.
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-[8px]">
        <span className="break-all text-[10px] text-mute">자료 ID · {record.id}</span>
        <div className="flex flex-wrap gap-[6px]">
          {current.parseStatus === 'COMPLETED' && (
            <Button
              variant="secondary"
              size="sm"
              disabled={retryIndex.isPending || detail.isFetching}
              onClick={() => retryIndex.mutate()}
            >
              {retryIndex.isPending ? '검색 준비 중…' : '검색 준비 다시 시도'}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            disabled={detail.isFetching || retryIndex.isPending}
            onClick={() => void detail.refetch()}
          >
            {detail.isFetching ? '상태 확인 중…' : '상태 다시 확인'}
          </Button>
        </div>
      </div>
    </li>
  )
}

export function RecordsPanel({ clubId, title = '회의 자료' }: { clubId: string; title?: string }) {
  return <ClubRecordsPanel key={clubId} clubId={clubId} title={title} />
}

function ClubRecordsPanel({ clubId, title }: { clubId: string; title: string }) {
  const { records, upload, refresh } = useRecordUploads(clubId)
  const [category, setCategory] = useState<RecordCategory>('ETC')
  const [file, setFile] = useState<File | null>(null)
  const [fileInputKey, setFileInputKey] = useState(0)
  const [validationError, setValidationError] = useState<string | null>(null)

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setValidationError(null)
    if (!file || !/\.(pdf|csv|xlsx)$/i.test(file.name)) {
      setValidationError('PDF, CSV, XLSX 파일을 선택해 주세요.')
      return
    }
    if (file.size === 0) {
      setValidationError('내용이 있는 파일을 선택해 주세요.')
      return
    }
    try {
      await upload.mutateAsync({ category, file })
      setFile(null)
      setFileInputKey((value) => value + 1)
    } catch {
      // 서버 오류는 mutation 상태로 표시한다. 파일을 유지해 재시도할 수 있다.
    }
  }

  return (
    <Card className="p-[20px]">
      <div className="mb-[18px] flex flex-col gap-[6px]">
        <h2 className="text-h2 text-ink">{title}</h2>
        <p className="text-[12px] leading-[19px] text-mute">
          자료를 올리고 검색 준비 상태를 확인해 주세요. 검색 준비가 완료된 자료만 회의 검색에 사용할
          수 있어요.
        </p>
      </div>

      <form onSubmit={(event) => void handleUpload(event)} className="flex flex-col gap-[13px]">
        <label className="flex flex-col gap-[7px] text-[11.5px] font-bold text-ink2">
          자료 분류
          <select
            aria-label="자료 분류"
            value={category}
            disabled={upload.isPending}
            onChange={(event) => setCategory(event.target.value as RecordCategory)}
            className="rounded-[11px] border border-soft bg-bg px-[12px] py-[11px] text-[13px] text-ink"
          >
            {RECORD_CATEGORIES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <Input
          key={fileInputKey}
          type="file"
          label="자료 파일 (PDF · CSV · XLSX)"
          accept=".pdf,.csv,.xlsx"
          disabled={upload.isPending}
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null)
            setValidationError(null)
            upload.reset()
          }}
        />
        <p className="text-[11px] leading-[18px] text-mute">
          스캔 이미지와 암호가 걸린 문서는 읽을 수 없어요.
        </p>
        {(validationError || upload.isError) && (
          <p role="alert" className="text-[12px] text-failed">
            {validationError ?? recordErrorMessage(upload.error)}
          </p>
        )}
        <Button type="submit" disabled={!file || upload.isPending || !clubId}>
          {upload.isPending ? '자료 올리고 읽는 중…' : '자료 올리기'}
        </Button>
        <span role="status" className="text-[11px] text-ink2">
          {upload.isSuccess ? '자료를 받았어요. 아래에서 처리 결과를 확인해 주세요.' : ''}
        </span>
      </form>

      <div className="mt-[20px] border-t border-line pt-[16px]">
        <div className="flex items-center justify-between gap-[10px]">
          <h3 className="text-[12px] font-bold text-ink2">
            팀 자료 {records.data ? `· ${records.data.length}건` : ''}
          </h3>
          <Button
            variant="ghost"
            size="sm"
            disabled={records.isFetching}
            onClick={() => void refresh()}
          >
            {records.isFetching ? '목록 확인 중…' : '목록 새로고침'}
          </Button>
        </div>
        {records.isPending && (
          <p role="status" className="py-[18px] text-[12px] text-mute">
            팀 자료를 불러오고 있어요.
          </p>
        )}
        {records.isError && (
          <p role="alert" className="py-[18px] text-[12px] text-failed">
            {recordErrorMessage(records.error)} 자료 목록을 불러오지 못했어요.
          </p>
        )}
        {records.data && records.data.length > 0 ? (
          <ul className="mt-[6px]" aria-live="polite">
            {records.data.map((record) => (
              <RecordStatusRow key={record.id} clubId={clubId} record={record} />
            ))}
          </ul>
        ) : records.isSuccess ? (
          <p className="py-[18px] text-[12px] text-mute">아직 이 팀에 올린 자료가 없어요.</p>
        ) : null}
      </div>
    </Card>
  )
}
