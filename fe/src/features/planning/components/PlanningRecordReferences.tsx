import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { downloadRecord } from '@/features/records/api'
import {
  referenceDocumentCount,
  recordLookupAnnouncement,
  uniqueEvidenceSources,
  type RecordEvidenceSource,
  type RecordLookup,
  type RecordLookupEntry,
} from '@/features/planning/recordReferences'
import { Card } from '@/shared/ui/Card'
import { Tori } from '@/shared/ui/Tori'

function Chevron({ className = '' }: { className?: string }) {
  return (
    <svg aria-hidden width="16" height="16" viewBox="0 0 20 20" fill="none" className={className}>
      <path
        d="m6 8 4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function SourceRow({ source, preview }: { source: RecordEvidenceSource; preview: boolean }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  return (
    <div className="space-y-1.5 py-2 first:pt-0 last:pb-0">
      <div className="flex items-start gap-2">
        <svg
          aria-hidden
          width="15"
          height="18"
          viewBox="0 0 20 24"
          fill="none"
          className="mt-0.5 shrink-0 text-blue-600"
        >
          <path
            d="M4 2h8l5 5v15H4V2Z M12 2v6h5 M7 12h7 M7 16h7"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
        <div className="min-w-0 flex-1">
          <p className="break-words text-[12px] leading-[18px] font-medium text-ink2">
            {source.fileName}
          </p>
          <p className="mt-0.5 break-words text-[12px] leading-[18px] text-mute">
            {source.location.label}
          </p>
        </div>
      </div>
      {preview ? (
        <p className="pl-[23px] text-[12px] text-mute">예시 자료</p>
      ) : (
        <button
          type="button"
          disabled={busy}
          aria-label={`${source.fileName} 원본 다운로드`}
          aria-busy={busy || undefined}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 text-[12px] font-semibold text-blue-700 underline-offset-4 hover:bg-blue-50 hover:underline disabled:cursor-wait disabled:opacity-60"
          onClick={async () => {
            if (busy) return
            setBusy(true)
            setError(false)
            try {
              await downloadRecord(source.recordId, source.fileName)
            } catch {
              setError(true)
            } finally {
              setBusy(false)
            }
          }}
        >
          <svg aria-hidden width="14" height="14" viewBox="0 0 20 20" fill="none">
            <path
              d="M10 3v9m-3-3 3 3 3-3 M4 13v4h12v-4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          {busy ? '받는 중…' : error ? '다운로드 다시 시도' : '원본 다운로드'}
        </button>
      )}
      {error && (
        <p role="alert" className="text-[12px] leading-5 text-failed">
          파일을 받지 못했어요. 권한과 연결 상태를 확인해 주세요.
        </p>
      )}
    </div>
  )
}

function Sources({ sources, preview }: { sources: RecordEvidenceSource[]; preview: boolean }) {
  const unique = uniqueEvidenceSources(sources)
  const rows = unique.map((source) => (
    <SourceRow
      key={JSON.stringify([source.recordId, source.location.label])}
      source={source}
      preview={preview}
    />
  ))
  if (unique.length === 1) return <div className="mt-3 border-t border-line/70 pt-3">{rows}</div>
  return (
    <details className="group/source mt-2">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1 rounded-md text-[12px] font-semibold text-blue-700 hover:underline [&::-webkit-details-marker]:hidden">
        출처 {unique.length}개 보기
        <Chevron className="transition-transform duration-150 group-open/source:rotate-180 motion-reduce:transition-none" />
      </summary>
      <div className="divide-y divide-line/70">{rows}</div>
    </details>
  )
}

function EvidenceFact({
  content,
  sources,
  preview,
}: {
  content: string
  sources: RecordEvidenceSource[]
  preview: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const id = useId()
  const long = content.length > 150
  return (
    <div className="py-4 first:pt-0 last:pb-0">
      <p
        id={id}
        className={`break-words text-[13px] leading-[22px] text-ink ${long && !expanded ? 'line-clamp-3' : ''}`}
      >
        {content}
      </p>
      {long && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={() => setExpanded((value) => !value)}
          className="min-h-11 text-[12px] font-medium text-blue-700 hover:underline"
        >
          {expanded ? '내용 접기' : '전체 내용 보기'}
        </button>
      )}
      <Sources sources={sources} preview={preview} />
    </div>
  )
}

function LookupContent({ lookup, preview }: { lookup: RecordLookup; preview: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const contentId = useId()
  if (lookup.status !== 'available') {
    const text =
      lookup.status === 'not_found'
        ? '이번 조회에서 관련 내용을 찾지 못했어요.'
        : lookup.status === 'failed'
          ? '기록을 불러오지 못했어요. 잠시 후 대화에서 다시 요청해 주세요.'
          : '이번 기록 조회를 진행하지 못했어요.'
    return (
      <div className="space-y-2">
        <p className="text-[13px] leading-[21px] text-ink2">{text}</p>
        {lookup.status === 'not_found' &&
          lookup.result?.notFound.map((item, index) => (
            <p key={index} className="break-words text-[12px] leading-5 text-mute">
              {item}
            </p>
          ))}
        {lookup.status === 'rejected' && lookup.reason && (
          <p className="break-words text-[12px] leading-5 text-mute">{lookup.reason}</p>
        )}
        {lookup.status === 'not_found' && (
          <Link
            to="/records"
            className="inline-flex min-h-11 items-center rounded-md text-[12px] font-semibold text-blue-700 underline underline-offset-4"
          >
            자료함 확인
          </Link>
        )}
      </div>
    )
  }
  if (!lookup.result)
    return (
      <p className="text-[13px] leading-[21px] text-mute">
        이 조회는 상세 출처가 저장되어 있지 않아요.
      </p>
    )
  const { facts, conflicts, notFound } = lookup.result
  return (
    <div className="space-y-4">
      <div id={contentId} className="divide-y divide-line">
        {(expanded ? facts : facts.slice(0, 2)).map((fact, index) => (
          <EvidenceFact
            key={index}
            content={fact.content}
            sources={fact.sources}
            preview={preview}
          />
        ))}
      </div>
      {facts.length > 2 && (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={() => setExpanded((value) => !value)}
          className="flex min-h-11 w-full items-center justify-center gap-1 rounded-lg border border-line text-[12px] font-medium text-ink2 hover:bg-bg"
        >
          {expanded ? '내용 접기' : `확인한 내용 ${facts.length - 2}개 더 보기`}
          <Chevron className={expanded ? 'rotate-180' : ''} />
        </button>
      )}
      {conflicts.length > 0 && (
        <div className="space-y-3 rounded-lg bg-pending-bg px-3.5 py-3">
          <p className="text-[12px] font-semibold text-pending">기록마다 내용이 달라요</p>
          {conflicts.map((conflict, index) => (
            <div key={index} className="space-y-3">
              <p className="break-words text-[13px] leading-5 text-ink">{conflict.description}</p>
              {conflict.values.map((value, valueIndex) => (
                <div key={valueIndex} className="border-t border-pending-line pt-3">
                  <p className="break-words text-[13px] leading-[21px] text-ink2">
                    {value.content}
                  </p>
                  <Sources sources={value.sources} preview={preview} />
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
      {notFound.length > 0 && (
        <div className="space-y-1.5 border-t border-line pt-3">
          <p className="text-[12px] font-semibold text-ink2">확인하지 못한 내용</p>
          {notFound.map((item, index) => (
            <p key={index} className="break-words text-[12px] leading-5 text-mute">
              {item}
            </p>
          ))}
        </div>
      )}
      {!facts.length && !conflicts.length && !notFound.length && (
        <p className="text-[13px] text-mute">표시할 상세 내용이 없어요.</p>
      )}
    </div>
  )
}

function lookupLabel(lookup: RecordLookup) {
  return (
    lookup.result?.facts[0]?.content ??
    lookup.result?.conflicts[0]?.description ??
    (lookup.status === 'not_found'
      ? '관련 내용을 찾지 못한 조회'
      : lookup.status === 'failed'
        ? '완료하지 못한 조회'
        : '상세 내용이 없는 조회')
  )
}

export function PlanningRecordReferences({
  entries,
  preview = false,
}: {
  entries: RecordLookupEntry[]
  preview?: boolean
}) {
  const [visible, setVisible] = useState(5)
  const latest = entries[0]
  // Keep the live region mounted before the first lookup. The count changes
  // once per saved search, including consecutive searches with the same outcome.
  const announcement = (
    <p role="status" aria-live="polite" aria-atomic="true" className="sr-only">
      {latest ? `저장된 조회 ${entries.length}건. ${recordLookupAnnouncement(latest.lookup)}` : ''}
    </p>
  )
  if (!latest) return announcement
  const previous = entries.slice(1)
  const count = referenceDocumentCount(entries)
  const hasConflict = Boolean(latest.lookup.result?.conflicts.length)
  return (
    <>
      {announcement}
      <Card className="min-w-0 overflow-hidden" aria-label="참고한 과거 기록">
        <header className="flex items-start gap-2.5 border-b border-line bg-blue-50/60 px-5 py-4">
          <Tori size={32} className="-ml-1" />
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
              <h2 className="text-h3 text-ink">참고한 과거 기록</h2>
              <span className="text-[12px] text-blue-700">
                {count ? `자료 ${count}개` : '최근 조회'}
              </span>
            </div>
            <p className="mt-1 text-[12px] leading-5 text-ink2">대화에서 찾아본 내용을 모았어요.</p>
          </div>
        </header>
        <div className="px-5 py-4">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-[12px] text-mute">
            <span>최근 조회</span>
            {latest.lookup.status === 'failed' && (
              <span className="font-medium text-failed">조회 실패</span>
            )}
            {latest.lookup.status === 'not_found' && <span>관련 내용 없음</span>}
            {hasConflict && <span className="font-medium text-pending">내용 차이 있음</span>}
          </div>
          <LookupContent key={latest.revision} lookup={latest.lookup} preview={preview} />
        </div>
        {previous.length > 0 && (
          <details className="group/history border-t border-line">
            <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 px-5 py-3 text-[12px] font-semibold text-ink2 hover:bg-bg [&::-webkit-details-marker]:hidden">
              이전 조회 {previous.length}건
              <Chevron className="transition-transform duration-150 group-open/history:rotate-180 motion-reduce:transition-none" />
            </summary>
            <div className="divide-y divide-line border-t border-line px-5">
              {previous.slice(0, visible).map((entry) => (
                <details key={entry.revision} className="group/entry py-1">
                  <summary className="flex min-h-14 cursor-pointer list-none items-center gap-2 py-3 text-[12px] leading-5 text-ink2 hover:text-blue-700 [&::-webkit-details-marker]:hidden">
                    <span className="line-clamp-2 min-w-0 flex-1 break-words">
                      {lookupLabel(entry.lookup)}
                    </span>
                    <Chevron className="shrink-0 transition-transform duration-150 group-open/entry:rotate-180 motion-reduce:transition-none" />
                  </summary>
                  <div className="pb-4">
                    <LookupContent lookup={entry.lookup} preview={preview} />
                  </div>
                </details>
              ))}
              {previous.length > visible && (
                <button
                  type="button"
                  onClick={() => setVisible((value) => value + 5)}
                  className="min-h-12 w-full text-[12px] font-semibold text-blue-700 hover:underline"
                >
                  이전 조회 {Math.min(5, previous.length - visible)}건 더 보기
                </button>
              )}
            </div>
          </details>
        )}
        <p className="border-t border-line px-5 py-3 text-[11px] leading-[18px] text-mute">
          과거 기록은 참고용이에요. 올해 조건은 대화로 정해요.
        </p>
      </Card>
    </>
  )
}
