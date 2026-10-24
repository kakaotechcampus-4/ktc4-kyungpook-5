// 사실·출처는 AI가 반환한 구조화된 검색 결과만 표시한다. 본문에서 출처를 추출하지 않는다.
import type { RecordLookup } from '@/features/planning/agent-playground'
import type { Fact } from '@/features/planning/playground'
import { Card } from '@/shared/ui/Card'

function SourceFact({ fact }: { fact: Fact }) {
  return (
    <div className="flex flex-col gap-1 border-b border-blue-200 pb-3 last:border-0 last:pb-0">
      <p className="whitespace-pre-wrap text-body text-ink2">{fact.content}</p>
      {fact.sources.map((source) => (
        <span
          key={`${source.record_id}:${source.location.label}`}
          className="text-caption text-mute"
        >
          {source.file_name} · {source.location.label}
        </span>
      ))}
    </div>
  )
}

export function AgentReferences({ lookup }: { lookup: RecordLookup | null }) {
  return (
    <Card className="flex flex-col gap-3 border-blue-200 bg-blue-50 p-5">
      <h2 className="text-h3 text-blue-700">참고한 과거 기록</h2>
      {!lookup && (
        <p className="text-caption text-ink2">샘플 기록을 준비하고 과거 행사에 관해 물어보세요.</p>
      )}
      {lookup?.query && <p className="text-caption text-mute">조회 질문: {lookup.query}</p>}
      {lookup?.status === 'failed' && (
        <p role="status" className="text-caption text-failed">
          기록 조회에 실패해 내용을 확인하지 못했어요.
        </p>
      )}
      {lookup?.status === 'rejected' && (
        <p role="status" className="text-caption text-failed">
          조회 요청을 처리하지 못했어요. 질문을 다시 말해 주세요.
        </p>
      )}
      {lookup?.result?.facts.map((fact, i) => (
        <SourceFact key={i} fact={fact} />
      ))}
      {lookup?.result?.conflicts.map((conflict, i) => (
        <div key={i} className="flex flex-col gap-2">
          <p className="font-bold text-pending">자료 차이: {conflict.description}</p>
          {conflict.values.map((fact, j) => (
            <SourceFact key={j} fact={fact} />
          ))}
        </div>
      ))}
      {!!lookup?.result?.not_found.length && (
        <p className="text-caption text-ink2">
          이번 검색에서 확인하지 못한 내용: {lookup.result.not_found.join(', ')}
        </p>
      )}
      {lookup && <p className="text-label text-mute">과거 행사 참고 자료 · 마지막 조회 기준</p>}
    </Card>
  )
}
