// 장부 표의 '행사' 칸 문구 (#367). 지출 응답에는 eventId만 있어 FE가 행사 목록으로 이름을 붙인다.
import type { EventSummary } from '@/features/events/types'
import { formatDotDate } from '@/shared/lib/format'

type EventForLabel = Pick<EventSummary, 'id' | 'title' | 'startDate'>

const UNNAMED = '이름 없는 행사'

const nameOf = (event: EventForLabel) => event.title.trim() || UNNAMED

/**
 * 행사 ID → 장부에 보일 이름.
 *
 * 이름이 같은 행사가 둘 이상이면 시작일을 붙여 구분한다(없으면 '날짜 미정').
 * 이름과 시작일까지 같으면 더 구분하지 않는다 — 목록 순서로 번호를 매기면
 * 행사가 늘 때 번호가 바뀌어 같은 지출의 표기가 흔들린다.
 */
export function eventLabels(events: EventForLabel[]): Map<string, string> {
  const counts = new Map<string, number>()
  for (const event of events) {
    const name = nameOf(event)
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  return new Map(
    events.map((event) => {
      const name = nameOf(event)
      if (counts.get(name) === 1) return [event.id, name]
      const date = event.startDate ? formatDotDate(event.startDate) : '날짜 미정'
      return [event.id, `${name} · ${date}`]
    }),
  )
}
