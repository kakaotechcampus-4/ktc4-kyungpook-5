import type { Decision, Suggestion, Transcript } from './types'

export type RecordCitation = {
  recordId: string
  fileName: string
  locationLabel: string
}

export type MeetingEvidenceFocus = {
  suggestionId: string
  title: string
  decisionId: string
  sourceId: string
  sourceVersion: number
}

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function recordCitation(value: unknown): RecordCitation | null {
  const citation = object(value)
  if (typeof citation?.recordId !== 'string' || !/^rec_[A-Za-z0-9]{1,22}$/.test(citation.recordId))
    return null
  const location = object(citation.location)
  return {
    recordId: citation.recordId,
    fileName: typeof citation.fileName === 'string' ? citation.fileName : '등록 자료',
    locationLabel: typeof location?.label === 'string' ? location.label : '',
  }
}

export function recordMatchesCitation(
  record: { id: string; clubId: string },
  citation: RecordCitation,
  clubId: string,
) {
  return record.id === citation.recordId && record.clubId === clubId
}

export function recordEvidenceBlocks(parseResult: unknown, locationLabel: string) {
  const value = object(parseResult)
  const blocks = (Array.isArray(value?.blocks) ? value.blocks : []).flatMap((block: unknown) => {
    const current = object(block)
    if (typeof current?.text !== 'string' || !current.text.trim()) return []
    const location = object(current.location)
    return [
      {
        text: current.text,
        locationLabel: typeof location?.label === 'string' ? location.label : '',
      },
    ]
  })
  let matching = locationLabel
    ? blocks.filter((block) => block.locationLabel === locationLabel)
    : blocks
  // 검색 청크의 CSV 범위는 모든 원본 행이 있을 때만 같은 위치로 확정한다.
  const range = !matching.length && /^([1-9]\d*)~([1-9]\d*)행$/.exec(locationLabel)
  if (range) {
    const first = Number(range[1])
    const last = Number(range[2])
    if (Number.isSafeInteger(first) && Number.isSafeInteger(last) && first <= last) {
      const rows = new Set<number>()
      const ranged = blocks.filter((block) => {
        const row = /^([1-9]\d*)행$/.exec(block.locationLabel)
        const number = row ? Number(row[1]) : NaN
        if (!Number.isSafeInteger(number) || number < first || number > last) return false
        rows.add(number)
        return true
      })
      if (rows.size === last - first + 1) matching = ranged
    }
  }
  return {
    blocks: matching.length ? matching : blocks,
    locationFound: !locationLabel || matching.length > 0,
  }
}

export function candidateEvidence(
  suggestion: Pick<Suggestion, 'decisionId' | 'evidence'>,
  meetingId: string,
  decisions: Decision[],
  transcripts: Transcript[],
): { decisionId: string; sources: Transcript[]; message: string | null } {
  const decision = decisions.find(
    (item) => item.id === suggestion.decisionId && item.meetingId === meetingId,
  )
  if (!decision || decision.status === 'STALE') {
    return {
      decisionId: suggestion.decisionId,
      sources: [],
      message: '이 후보의 현재 회의 근거를 찾지 못했어요. 회의 내용을 다시 불러와 주세요.',
    }
  }
  const references = suggestion.evidence.length ? suggestion.evidence : decision.sources
  const sources: Transcript[] = []
  let unavailable = false
  for (const reference of references) {
    const ref = object(reference)
    const valid =
      typeof ref?.sourceId === 'string' &&
      Number.isInteger(ref.sourceVersion) &&
      Number(ref.sourceVersion) > 0
    const belongs =
      valid &&
      decision.sources.some(
        (source) => source.sourceId === ref.sourceId && source.sourceVersion === ref.sourceVersion,
      )
    const transcript =
      belongs &&
      transcripts.find(
        (item) =>
          item.final && item.sourceId === ref.sourceId && item.sourceVersion === ref.sourceVersion,
      )
    if (!transcript) unavailable = true
    else if (!sources.some((item) => item.id === transcript.id)) sources.push(transcript)
  }
  return {
    decisionId: decision.id,
    sources: sources.sort((a, b) => a.seq - b.seq),
    message:
      unavailable || !sources.length
        ? '일부 근거 발화가 수정되었거나 없어 현재 내용으로 연결할 수 없어요.'
        : null,
  }
}
