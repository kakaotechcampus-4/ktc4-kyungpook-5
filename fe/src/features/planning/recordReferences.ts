import type { components } from '@/shared/api/schema'

type S = components['schemas']
export type RecordLookup = S['RecordLookupOut']
export type RecordLookupEntry = S['RecordLookupHistoryOut']
export type RecordEvidenceSource = S['RecordEvidenceSourceOut']

// Use only committed product snapshots. A null turn means “no new lookup”,
// while an explicit failure replaces the latest result without erasing history.
export function planningRecordHistory(
  screen: S['PlanScreenOut'] | undefined,
  view: S['PlanViewOut'] | null,
): RecordLookupEntry[] {
  const history = [...(screen?.recordLookupHistory ?? [])]
  if (!history.length && screen?.lastRecordLookup) {
    history.push({ revision: 0, lookup: screen.lastRecordLookup })
  }
  if (view?.recordLookup && view.baseRevision >= (screen?.baseRevision ?? 0)) {
    const index = history.findIndex((entry) => entry.revision === view.baseRevision)
    const entry = { revision: view.baseRevision, lookup: view.recordLookup }
    if (index === -1) history.push(entry)
    else history[index] = entry
  }
  return history.sort((a, b) => b.revision - a.revision)
}

export function uniqueEvidenceSources(sources: RecordEvidenceSource[]): RecordEvidenceSource[] {
  const seen = new Set<string>()
  return sources.filter((source) => {
    const key = JSON.stringify([source.recordId, source.location.label])
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function lookupSources(lookup: RecordLookup): RecordEvidenceSource[] {
  if (!lookup.result) return []
  return uniqueEvidenceSources([
    ...lookup.result.facts.flatMap((fact) => fact.sources),
    ...lookup.result.conflicts.flatMap((conflict) =>
      conflict.values.flatMap((value) => value.sources),
    ),
  ])
}

export function referenceDocumentCount(entries: RecordLookupEntry[]): number {
  return new Set(
    entries.flatMap((entry) => lookupSources(entry.lookup).map((source) => source.recordId)),
  ).size
}

export function recordLookupAnnouncement(lookup: RecordLookup): string {
  if (lookup.status === 'failed') return '기록을 불러오지 못했어요.'
  if (lookup.status === 'not_found') return '이번 조회에서 관련 내용을 찾지 못했어요.'
  if (lookup.status === 'rejected') return '이번 기록 조회를 진행하지 못했어요.'
  if (!lookup.result) return '이 조회는 상세 출처가 저장되어 있지 않아요.'
  if (lookup.result.conflicts.length)
    return '기록을 확인했어요. 자료마다 내용이 다른 항목이 있어요.'
  return '기록과 출처를 확인할 수 있어요.'
}
