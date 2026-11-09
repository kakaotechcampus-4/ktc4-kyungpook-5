// 자료 찾기 답. 토리가 자료에서 확인한 사실마다 출처를 붙이고, 검색된 자료와 원본 받기를 함께 보인다.
// 다른 답은 카드로 그리고, 이 답만 출처 목록 때문에 따로 그린다.
import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { dashboardApi } from '@/features/dashboard/api'
import type { components } from '@/shared/api/schema'
import { Button } from '@/shared/ui/Button'

type Result = components['schemas']['ToriMessageOut']

export function RecordReply({ result }: { result: Result }) {
  const [downloadError, setDownloadError] = useState('')
  const [downloading, setDownloading] = useState<string | null>(null)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [selectedSources, setSelectedSources] = useState<number[]>([])
  const sourceListId = useId()
  const answer = result.recordAnswer
  const sourceItems = [
    ...(answer?.facts ?? []),
    ...(answer?.conflicts ?? []).flatMap((item) => item.values),
  ].flatMap((item) => item.sources)
  const sources = Array.from(
    new Map(
      sourceItems.map((source) => [
        JSON.stringify([source.recordId, source.location?.label]),
        source,
      ]),
    ).values(),
  )
  const sourceNumbers = (items: typeof sources) => [
    ...new Set(
      items.map(
        (source) =>
          sources.findIndex(
            (item) =>
              item.recordId === source.recordId && item.location?.label === source.location?.label,
          ) + 1,
      ),
    ),
  ]
  const references = (items: typeof sources) => {
    const numbers = sourceNumbers(items)
    return (
      <button
        type="button"
        className="ml-2 text-caption font-semibold text-blue-700 underline"
        onClick={() => {
          setSelectedSources(numbers)
          setSourcesOpen(true)
          requestAnimationFrame(() =>
            document.getElementById(sourceListId)?.scrollIntoView({ block: 'nearest' }),
          )
        }}
        aria-label={`출처 ${numbers.join(', ')} 보기`}
      >
        [{numbers.slice(0, 3).join(', ')}
        {numbers.length > 3 ? ` 외 ${numbers.length - 3}곳` : ''}]
      </button>
    )
  }
  return (
    <div className="min-w-0 space-y-4 text-[14px] leading-6">
      <p role={answer?.status === 'failed' ? 'alert' : undefined} className="whitespace-pre-wrap">
        {result.reply}
      </p>
      {answer && (
        <div className="space-y-3">
          {answer.facts?.map((fact, index) => (
            <p key={index} className="whitespace-pre-wrap break-words">
              {fact.text}
              {references(fact.sources)}
            </p>
          ))}
          {answer.conflicts?.map((conflict, index) => (
            <div key={index} className="space-y-1">
              <p className="font-semibold">자료 간 내용이 달라요: {conflict.description}</p>
              {conflict.values.map((value, valueIndex) => (
                <p key={valueIndex} className="break-words">
                  {value.text}
                  {references(value.sources)}
                </p>
              ))}
            </div>
          ))}
          {sources.length > 0 && (
            <details
              id={sourceListId}
              open={sourcesOpen}
              onToggle={(event) => setSourcesOpen(event.currentTarget.open)}
              className="border-t border-line pt-2"
            >
              <summary className="cursor-pointer text-caption font-semibold text-blue-700">
                답변 출처 {sources.length}곳
              </summary>
              <ol className="mt-2 space-y-2">
                {sources.map((source, index) => (
                  <li
                    key={JSON.stringify([source.recordId, source.location?.label])}
                    className="text-caption"
                  >
                    <span className="break-all">
                      [{index + 1}] {source.fileName}
                    </span>{' '}
                    | {source.location?.label ?? '위치 정보 없음'}{' '}
                    {selectedSources.includes(index + 1) && (
                      <span className="font-semibold text-blue-700">이 내용의 출처 | </span>
                    )}
                    <button
                      type="button"
                      className="text-blue-700 underline"
                      disabled={!!downloading}
                      onClick={() => {
                        setDownloading(source.recordId)
                        setDownloadError('')
                        void dashboardApi
                          .download(source.recordId, source.fileName)
                          .catch(() =>
                            setDownloadError(
                              '원본을 받지 못했어요. 권한과 파일 상태를 확인해 주세요.',
                            ),
                          )
                          .finally(() => setDownloading(null))
                      }}
                    >
                      {downloading === source.recordId ? '받는 중…' : '원본 다운로드'}
                    </button>
                  </li>
                ))}
              </ol>
            </details>
          )}
          {(answer.status !== 'answered' ||
            answer.semanticStatus !== 'AVAILABLE' ||
            answer.unindexedCount > 0 ||
            answer.candidateLimitReached ||
            answer.lexicalOmitted ||
            answer.filenameOnlyUnanalyzedCount > 0 ||
            !!answer.notFound?.length) && (
            <details className="text-caption text-ink2">
              <summary className="cursor-pointer font-semibold">답변 확인 사항</summary>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {answer.status === 'partial' && <li>일부 내용만 확인했어요.</li>}
                {answer.status === 'insufficient' && (
                  <li>검색된 자료만으로는 답을 확인하기 어려워요.</li>
                )}
                {answer.status === 'failed' && <li>자료를 바탕으로 답변을 만들지 못했어요.</li>}
                {answer.semanticStatus === 'UNAVAILABLE' && (
                  <li>답변을 위한 AI 검색을 사용할 수 없었어요.</li>
                )}
                {answer.semanticStatus === 'NO_INDEXED_RECORDS' && (
                  <li>AI 색인이 준비된 자료가 없어요.</li>
                )}
                {answer.unindexedCount > 0 && (
                  <li>AI 색인이 준비되지 않은 자료가 {answer.unindexedCount}개 있어요.</li>
                )}
                {answer.candidateLimitReached && <li>검색 후보 한도에 도달했어요.</li>}
                {answer.lexicalOmitted && (
                  <li>일치하는 본문 중 일부를 답변에 사용하지 못했어요.</li>
                )}
                {answer.filenameOnlyUnanalyzedCount > 0 && (
                  <li>
                    파일명으로 찾은 자료 중 {answer.filenameOnlyUnanalyzedCount}개는 답변 분석에
                    포함되지 않았어요. 원본을 확인해 주세요.
                  </li>
                )}
                {answer.notFound?.map((item, index) => (
                  <li key={index}>확인하지 못한 내용: {item}</li>
                ))}
              </ul>
            </details>
          )}
          {answer.semanticStatus === 'UNAVAILABLE' && (
            <p role="alert" className="text-caption text-failed">
              AI 검색을 사용할 수 없어 답변이 제한될 수 있어요.
            </p>
          )}
        </div>
      )}
      {downloadError && (
        <p role="alert" className="text-failed">
          {downloadError}
        </p>
      )}
      {result.records && (
        <div className="space-y-3">
          <p className="border-t border-line pt-4 text-caption font-semibold text-ink2">
            검색된 자료 {result.recordTotalCount ?? 0}건{' '}
            {result.recordTotalCount && result.recordTotalCount > result.records.items.length
              ? `중 ${result.records.items.length}건 표시`
              : ''}
          </p>
          {result.records.semanticStatus === 'UNAVAILABLE' &&
            answer?.semanticStatus !== 'UNAVAILABLE' && (
              <p
                role="alert"
                className="rounded-lg border border-failed-line bg-failed-bg px-3 py-2 text-failed"
              >
                AI 추천을 불러오지 못해 파일명과 본문 일치 결과만 표시해요.
              </p>
            )}
          {!answer && result.records.semanticStatus === 'NO_INDEXED_RECORDS' && (
            <p className="rounded-lg bg-bg px-3 py-2 text-ink2">
              AI 검색 준비가 된 자료가 없어 파일명과 읽은 본문만 검색했어요.
            </p>
          )}
          {!answer && result.records.unindexedCount > 0 && (
            <p className="text-mute">
              {result.records.unindexedCount}개 자료는 AI 검색 준비 전이에요.
            </p>
          )}
          {!answer && result.records.semanticStatus === 'AVAILABLE' && (
            <p className="text-mute">
              AI 추천은 상위 {result.records.semanticCandidateLimit}개 청크를 바탕으로 한 후보예요.
            </p>
          )}
          {result.records.items.length === 0 ? (
            <p className="text-mute">
              {result.records.semanticStatus === 'UNAVAILABLE'
                ? '파일명과 본문 일치 결과가 없어요. AI 추천은 확인하지 못했어요.'
                : result.records.semanticStatus === 'NO_INDEXED_RECORDS'
                  ? '파일명과 본문 일치 결과가 없어요. AI 검색 준비가 된 자료는 없어요.'
                  : '검색 조건에 맞는 자료를 찾지 못했어요.'}
            </p>
          ) : (
            <details className="rounded-lg border border-line bg-card p-3">
              <summary className="cursor-pointer font-semibold">
                검색된 자료 보기 ({result.records.items.length}건)
              </summary>
              <div className="mt-3 space-y-3">
                {result.records.items.map((item) => (
                  <div
                    key={item.id}
                    className="space-y-2 rounded-lg border border-line bg-card p-4"
                  >
                    <p className="break-all font-bold">{item.fileName}</p>
                    <p className="text-mute">
                      {item.matchTypes
                        .map((type) =>
                          type === 'SEMANTIC'
                            ? 'AI 추천'
                            : type === 'CONTENT'
                              ? '본문 일치'
                              : '파일명 일치',
                        )
                        .join(' | ')}
                    </p>
                    {item.excerpts.map((excerpt, index) => (
                      <p key={index} className="whitespace-pre-wrap break-words">
                        {excerpt.text}
                        <span className="block text-mute">
                          {excerpt.location?.label ?? '위치 정보 없음'}
                        </span>
                      </p>
                    ))}
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={!!downloading}
                      onClick={() => {
                        setDownloading(item.id)
                        setDownloadError('')
                        void dashboardApi
                          .download(item.id, item.fileName)
                          .catch(() =>
                            setDownloadError(
                              '원본을 받지 못했어요. 권한과 파일 상태를 확인해 주세요.',
                            ),
                          )
                          .finally(() => setDownloading(null))
                      }}
                    >
                      {downloading === item.id ? '받는 중…' : '원본 다운로드'}
                    </Button>
                  </div>
                ))}
              </div>
            </details>
          )}
          <Link className="text-blue-700 underline" to="/records">
            자료함에서 검색하기
          </Link>
        </div>
      )}
    </div>
  )
}
