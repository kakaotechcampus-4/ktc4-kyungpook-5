import { useState, type FormEvent } from 'react'
import { downloadRecord } from '@/features/records/api'
import { useRecordSearch } from '@/features/records/hooks'
import { formatFileSize, RECORD_STATUS } from '@/features/records/presentation'
import type { components } from '@/shared/api/schema'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'

type Item = components['schemas']['RecordSearchItem']
const MATCH_LABEL = { FILENAME: '파일명 일치', CONTENT: '본문 일치', SEMANTIC: 'AI 추천' } as const

function SearchResult({ item }: { item: Item }) {
  const [downloading, setDownloading] = useState(false)
  const [failed, setFailed] = useState(false)
  return (
    <li className="space-y-2 border-t border-line py-4 first:border-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="break-all text-h3">{item.fileName}</h3>
        <Button
          variant="secondary"
          size="sm"
          disabled={downloading}
          onClick={() => {
            setFailed(false)
            setDownloading(true)
            void downloadRecord(item.id, item.fileName)
              .catch(() => setFailed(true))
              .finally(() => setDownloading(false))
          }}
        >
          {downloading ? '받는 중…' : '원본 다운로드'}
        </Button>
      </div>
      <p className="text-caption text-mute">
        {item.fileType} · {formatFileSize(item.size)} · {RECORD_STATUS[item.parseStatus].label}
      </p>
      <p className="text-caption font-bold text-blue-700">
        {item.matchTypes.map((type) => MATCH_LABEL[type]).join(' · ')}
      </p>
      {item.excerpts.map((excerpt, index) => (
        <div key={index} className="rounded-xl bg-bg p-3 text-caption leading-6">
          <p className="whitespace-pre-wrap break-words">{excerpt.text}</p>
          <p className="mt-1 text-mute">{excerpt.location?.label ?? '위치 정보 없음'}</p>
        </div>
      ))}
      {failed && (
        <p role="alert" className="text-caption text-failed">
          원본을 받지 못했어요. 접근 권한과 파일 상태를 확인해 주세요.
        </p>
      )}
    </li>
  )
}

export function RecordSearch({ clubId, userId }: { clubId: string; userId: string }) {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const results = useRecordSearch(clubId, userId, query, page)
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const value = input.trim()
    if (!value) return
    if (value === query && page === 1) void results.refetch()
    else {
      setPage(1)
      setQuery(value)
    }
  }
  const data = results.data?.data
  const meta = results.data?.meta
  const pageCount = Math.max(1, Math.ceil((meta?.totalCount ?? 0) / 20))
  return (
    <Card className="space-y-4 p-5">
      <div>
        <h2 className="text-h2">자료 통합검색</h2>
        <p className="mt-1 text-caption text-mute">
          선택한 팀의 파일 이름과 읽은 내용, AI 추천 자료를 찾아요.
        </p>
      </div>
      <form className="flex items-end gap-2" onSubmit={submit}>
        <div className="min-w-0 flex-1">
          <Input
            label="검색어"
            placeholder="찾고 싶은 내용이나 파일 이름"
            maxLength={200}
            value={input}
            onChange={(event) => setInput(event.target.value)}
          />
        </div>
        <Button type="submit" disabled={!input.trim() || results.isFetching}>
          검색
        </Button>
      </form>
      {!query && <p className="text-caption text-mute">검색어를 입력해 주세요.</p>}
      {query && results.isFetching && (
        <p role="status" className="text-caption">
          자료를 검색하고 있어요…
        </p>
      )}
      {query && results.isError && (
        <div role="alert" className="text-caption text-failed">
          검색 결과를 불러오지 못했어요. 연결과 소속 권한을 확인해 주세요.{' '}
          <button className="underline" onClick={() => void results.refetch()}>
            다시 시도
          </button>
        </div>
      )}
      {data && !results.isError && !results.isFetching && (
        <>
          <p role="status" className="text-caption text-ink2">
            ‘{query}’ 검색 결과 {meta?.totalCount ?? 0}건
          </p>
          {data.semanticStatus === 'UNAVAILABLE' && (
            <p role="alert" className="text-caption text-failed">
              AI 추천을 불러오지 못해 파일명과 본문 일치 결과만 표시해요. 다시 검색해 주세요.
            </p>
          )}
          {data.semanticStatus === 'NO_INDEXED_RECORDS' && (
            <p className="text-caption text-mute">
              AI 검색이 준비된 자료가 없어 파일명과 읽은 본문만 검색했어요.
            </p>
          )}
          {data.unindexedCount > 0 && (
            <p className="text-caption text-mute">
              {data.unindexedCount}개 자료는 AI 검색 준비 전이에요. 파일명과 읽은 본문은 검색할 수
              있어요.
            </p>
          )}
          {data.semanticStatus === 'AVAILABLE' && (
            <p className="text-caption text-mute">
              AI 추천은 검색 준비된 자료의 관련 청크 최대 {data.semanticCandidateLimit}개를 기준으로
              하며, 관련 자료 전체를 보장하지 않아요.
            </p>
          )}
          {data.items.length ? (
            <ul>
              {data.items.map((item) => (
                <SearchResult key={item.id} item={item} />
              ))}
            </ul>
          ) : (
            <p className="py-4 text-caption text-mute">
              일치하는 자료가 없어요. 다른 검색어를 입력해 보세요.
            </p>
          )}
          {(pageCount > 1 || page > 1) && (
            <nav aria-label="검색 결과 페이지" className="flex items-center justify-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((current) => current - 1)}
              >
                이전
              </Button>
              <span className="text-caption">
                {page} / {pageCount}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= pageCount}
                onClick={() => setPage((current) => current + 1)}
              >
                다음
              </Button>
            </nav>
          )}
        </>
      )}
    </Card>
  )
}
