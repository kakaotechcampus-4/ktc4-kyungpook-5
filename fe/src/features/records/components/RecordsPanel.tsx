import { useState, type FormEvent } from 'react'
import { downloadRecord, RECORD_PAGE_SIZE } from '@/features/records/api'
import {
  useDeleteRecord,
  useRecordCounts,
  useRecordDetail,
  useRecordUploads,
  useRetryRecordIndex,
} from '@/features/records/hooks'
import {
  formatFileSize,
  parseErrorMessage,
  RECORD_CATEGORIES,
  recordErrorMessage,
  RECORD_STATUS,
} from '@/features/records/presentation'
import type { ClubRecord, RecordCategory, RecordFilter } from '@/features/records/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { Input } from '@/shared/ui/Input'
import { Skeleton } from '@/shared/ui/Skeleton'
import { staggerDelay } from '@/shared/lib/stagger'

const FILTERS: Array<{ value: RecordFilter; label: string }> = [
  { value: 'ALL', label: '전체' },
  ...RECORD_CATEGORIES,
]

function RecordStatusRow({
  clubId,
  record,
  listUpdatedAt,
  index,
}: {
  clubId: string
  record: ClubRecord
  listUpdatedAt: number
  index: number
}) {
  const detail = useRecordDetail(clubId, record.id, record.parseStatus)
  const retryIndex = useRetryRecordIndex(clubId, record.id)
  const remove = useDeleteRecord(clubId)
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState(false)
  // 상세와 목록 중 더 최근에 받은 쪽을 보여 준다. 예전에 받아 둔 상세가 새 목록 상태를 덮지 않고,
  // 「상태 다시 확인」·폴링으로 새로 받은 상세는 바로 보인다.
  const current = detail.data && detail.dataUpdatedAt > listUpdatedAt ? detail.data : record
  const status = RECORD_STATUS[current.parseStatus]

  return (
    <li
      className="flex flex-col gap-[9px] border-t border-line py-[16px] first:border-0 animate-turn-in motion-reduce:animate-none"
      style={{ animationDelay: staggerDelay(index) }}
    >
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
      {downloadError && (
        <p role="alert" className="text-[12px] text-failed">
          원본 파일을 받지 못했어요. 접근 권한과 파일 상태를 확인해 주세요.
        </p>
      )}
      {retryIndex.isError && (
        <p role="alert" className="text-[12px] text-failed">
          {recordErrorMessage(retryIndex.error)} 검색 준비 재시도가 완료되지 않았어요.
        </p>
      )}
      {remove.isError && (
        <p role="alert" className="text-[12px] text-failed">
          {recordErrorMessage(remove.error)} 자료를 지우지 못했어요.
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-[8px]">
        <span className="break-all text-[10px] text-mute">자료 ID · {record.id}</span>
        <div className="flex flex-wrap gap-[6px]">
          <Button
            variant="secondary"
            size="sm"
            disabled={downloading}
            onClick={() => {
              setDownloading(true)
              setDownloadError(false)
              void downloadRecord(record.id, current.fileName)
                .catch(() => setDownloadError(true))
                .finally(() => setDownloading(false))
            }}
          >
            {downloading ? '받는 중…' : '원본 다운로드'}
          </Button>
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
          {/* 되돌릴 수 없어 파일 이름을 물어보는 문구에 넣는다. 지우면 검색에서도 빠진다. */}
          <Button
            variant="danger"
            size="sm"
            disabled={remove.isPending}
            onClick={() => {
              if (
                window.confirm(
                  `${current.fileName}을(를) 지울까요? 원본 파일과 검색 결과가 함께 사라지고 되돌릴 수 없어요.`,
                )
              ) {
                remove.mutate(record.id)
              }
            }}
          >
            {remove.isPending ? '지우는 중…' : '삭제'}
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
  const [page, setPage] = useState(1)
  const [filter, setFilter] = useState<RecordFilter>('ALL')
  const { records, upload, refresh } = useRecordUploads(
    clubId,
    page,
    filter === 'ALL' ? undefined : filter,
  )
  const counts = useRecordCounts(clubId)
  const rows = records.data?.data
  const totalCount = records.data?.meta?.totalCount ?? rows?.length ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / RECORD_PAGE_SIZE))
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
      // 다른 분류를 보고 있으면 방금 올린 자료가 안 보여 실패한 줄 안다. 전체로 돌린다.
      // 올리는 동안 칩을 바꿨을 수 있어 지금 고른 분류와 비교한다.
      setFilter((current) => (current === category ? current : 'ALL'))
      setPage(1)
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
            팀 자료 {counts.ALL === undefined ? '' : `${counts.ALL}건`}
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
        <div
          role="group"
          aria-label="자료 분류로 보기"
          className="mt-[10px] flex flex-wrap gap-[6px]"
        >
          {FILTERS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => {
                setFilter(value)
                setPage(1)
                // 「아래에서 처리 결과를 확인」 안내가 올린 자료가 없는 목록 위에 남지 않게 한다.
                if (upload.isSuccess) upload.reset()
              }}
              className={cn(
                'rounded-[8px] border px-[11px] py-[6px] text-[12px] transition-colors duration-150 motion-reduce:transition-none',
                filter === value
                  ? 'border-blue-600 bg-blue-600 font-bold text-white'
                  : 'border-soft bg-card font-medium text-ink2 hover:bg-bg',
              )}
            >
              {label}
              {counts[value] !== undefined && (
                <>
                  {' '}
                  {counts[value]}
                  <span className="sr-only">건</span>
                </>
              )}
            </button>
          ))}
        </div>
        {records.isPending && (
          <ul className="mt-[6px]" role="status" aria-busy>
            <li className="sr-only">팀 자료를 불러오고 있어요.</li>
            {[0, 1, 2].map((i) => (
              <li
                key={i}
                className="flex flex-col gap-[9px] border-t border-line py-[16px] first:border-0"
              >
                <Skeleton className="h-[18px] w-[240px]" />
                <Skeleton className="h-[14px] w-[160px]" />
                <Skeleton className="h-[17px] w-full max-w-[420px]" />
              </li>
            ))}
          </ul>
        )}
        {records.isError && (
          <p role="alert" className="py-[18px] text-[12px] text-failed">
            {recordErrorMessage(records.error)} 자료 목록을 불러오지 못했어요.
          </p>
        )}
        {rows && rows.length > 0 ? (
          <ul className="mt-[6px]" aria-live="polite">
            {rows.map((record, i) => (
              <RecordStatusRow
                key={record.id}
                clubId={clubId}
                record={record}
                listUpdatedAt={records.dataUpdatedAt}
                index={i}
              />
            ))}
          </ul>
        ) : records.isSuccess ? (
          <p className="py-[18px] text-[12px] text-mute">
            {page > 1
              ? '이 페이지에 표시할 자료가 없어요. 이전 페이지를 확인해 주세요.'
              : filter === 'ALL'
                ? '아직 이 팀에 올린 자료가 없어요.'
                : '이 분류로 올린 자료가 없어요.'}
          </p>
        ) : null}
        {records.data && (pageCount > 1 || page > 1) && (
          <nav
            aria-label="자료 목록 페이지"
            className="mt-3 flex items-center justify-center gap-3"
          >
            <Button
              variant="secondary"
              size="sm"
              disabled={page <= 1 || records.isFetching}
              onClick={() => setPage((current) => current - 1)}
            >
              이전
            </Button>
            <span className="text-[12px] text-ink2">
              {page} / {pageCount}
            </span>
            <Button
              variant="secondary"
              size="sm"
              disabled={page >= pageCount || records.isFetching}
              onClick={() => setPage((current) => current + 1)}
            >
              다음
            </Button>
          </nav>
        )}
      </div>
    </Card>
  )
}
