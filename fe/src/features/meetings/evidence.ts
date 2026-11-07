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
  const matching = locationLabel
    ? blocks.filter((block) => block.locationLabel === locationLabel)
    : blocks
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
