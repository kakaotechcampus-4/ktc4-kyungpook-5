// 토리 답변 글을 화면에 그릴 덩어리로 나눈다(#304).
// 모델은 답변에 마크다운 일부를 쓴다. 저장된 답변 46개에서 본 것은 굵게(**), 목록(- , 들여쓴 하위 목록),
// 빈 줄 문단, 줄 끝 공백 두 칸 줄바꿈뿐이었다. 그 범위만 해석하고 나머지 기호는 글자 그대로 둔다.
// HTML은 만들지 않고 구조만 돌려준다. 답변 글을 HTML로 넣지 않으므로 글 속 꺾쇠가 태그가 되지 않는다.
//
//   "초안 만들었어요!\n\n- **인원:** 40명\n- **장소:** 미정"
//   → [ { kind: 'p', lines: [[{ text: '초안 만들었어요!' }]] },
//       { kind: 'list', ordered: false, items: [
//           { text: [{ text: '인원:', bold: true }, { text: ' 40명' }] },
//           { text: [{ text: '장소:', bold: true }, { text: ' 미정' }] } ] } ]

export interface Span {
  text: string
  bold?: boolean
}

export interface ListItem {
  text: Span[]
  children?: ReplyList
}

export interface ReplyList {
  kind: 'list'
  ordered: boolean
  // 항목 사이에 빈 줄이 있던 목록. 항목마다 묶음이 커서 간격을 더 둔다.
  loose?: boolean
  items: ListItem[]
}

export interface ReplyParagraph {
  kind: 'p'
  // 문단 안의 한 줄씩. 화면에서 줄바꿈으로 잇는다.
  lines: Span[][]
}

export type ReplyBlock = ReplyParagraph | ReplyList

// "- 항목", "* 항목", "• 항목", "1. 항목", "2) 항목". 받는 중이면 기호만 먼저 온 "- "도 목록 줄로 본다.
const LIST_LINE = /^(\s*)([-*•]|\d{1,3}[.)])(?:\s+(.*))?$/
// 제목(#)은 본 적 없지만 오면 기호를 빼고 굵은 문단으로 보인다.
const HEADING_LINE = /^#{1,6}\s+(.*)$/

// 굵게(**)를 짝지어 나눈다. 짝이 없는 마지막 **는 받는 중에 닫는 기호가 아직 오지 않은 것으로 보고
// 그 뒤를 굵게 둔다. 그래야 "**40"이 "**40**"으로 바뀔 때 별표가 보였다 사라지지 않는다.
export function parseSpans(line: string, partial = false): Span[] {
  let source = line
  // 받는 중 끝에 별표 하나만 온 상태("…은 *")는 다음 조각에서 **가 될 수 있어 잠시 숨긴다.
  if (partial && /(^|[^*])\*$/.test(source)) source = source.slice(0, -1)
  const parts = source.split('**')
  const spans: Span[] = []
  parts.forEach((text, index) => {
    if (!text) return
    const bold = index % 2 === 1
    const last = spans.at(-1)
    if (last && !!last.bold === bold) last.text += text
    else spans.push(bold ? { text, bold } : { text })
  })
  return spans
}

function emptySpans(spans: Span[]) {
  return spans.every((span) => !span.text.trim())
}

// partial: 아직 받는 중인 답변. 마지막 줄이 덜 왔을 수 있다.
export function parseReply(text: string, partial = false): ReplyBlock[] {
  const blocks: ReplyBlock[] = []
  // 줄 끝 공백(마크다운의 "두 칸 줄바꿈")은 화면에서 의미가 없어 지운다.
  const lines = text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => line.trimEnd())
  let paragraph: ReplyParagraph | null = null
  let list: ReplyList | null = null
  // 목록 뒤 빈 줄. 다음 줄도 같은 목록 항목이면 이어 가고, 아니면 목록을 닫는다.
  let gap = false
  // 하위 목록을 열게 한 들여쓰기. 위 항목보다 깊으면 하위로 본다.
  let baseIndent = 0

  lines.forEach((line, index) => {
    const isLast = index === lines.length - 1
    const spansOf = (raw: string) => parseSpans(raw, partial && isLast)
    if (!line.trim()) {
      paragraph = null
      gap = true
      return
    }
    const item = LIST_LINE.exec(line)
    if (item) {
      const indent = item[1].length
      const ordered = /\d/.test(item[2])
      const entry: ListItem = { text: spansOf(item[3] ?? '') }
      if (list && gap && indent <= baseIndent && list.ordered === ordered) list.loose = true
      gap = false
      if (list && indent > baseIndent && list.items.length > 0) {
        const parent = list.items[list.items.length - 1]
        parent.children ??= { kind: 'list', ordered, items: [] }
        parent.children.items.push(entry)
        return
      }
      if (!list || list.ordered !== ordered) {
        paragraph = null
        list = { kind: 'list', ordered, items: [] }
        blocks.push(list)
        baseIndent = indent
      }
      list.items.push(entry)
      return
    }
    // 목록 바로 아래 들여쓴 글은 마지막 항목에 이어 붙인다(항목이 두 줄로 나뉜 경우).
    if (list && !gap && /^\s+/.test(line) && list.items.length > 0) {
      const target = list.items[list.items.length - 1]
      const tail = target.children?.items.at(-1) ?? target
      tail.text.push({ text: ' ' }, ...spansOf(line.trim()))
      return
    }
    list = null
    gap = false
    const heading = HEADING_LINE.exec(line)
    const spans = heading
      ? parseSpans(heading[1].replaceAll('**', ''), false).map((span) => ({ ...span, bold: true }))
      : spansOf(line)
    if (emptySpans(spans)) return
    if (!paragraph || heading) {
      paragraph = { kind: 'p', lines: [] }
      blocks.push(paragraph)
    }
    paragraph.lines.push(spans)
    if (heading) paragraph = null
  })
  return blocks
}
