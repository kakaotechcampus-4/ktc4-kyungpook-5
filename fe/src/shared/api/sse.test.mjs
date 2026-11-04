// Run: node --test src/shared/api/sse.test.mjs  (Node 22는 --experimental-strip-types를 붙인다)
import assert from 'node:assert/strict'
import test from 'node:test'
import { createSseParser } from './sse.ts'

function parseAll(chunks) {
  const events = []
  const parser = createSseParser((event) => events.push(event))
  for (const chunk of chunks) parser.push(chunk)
  parser.end()
  return events
}

test('이벤트 이름과 data를 빈 줄 단위로 나눈다', () => {
  const events = parseAll([
    'event: progress\ndata: {"kind":"condition_applied"}\n\n',
    'event: done\ndata: {"reply":"끝"}\n\n',
  ])
  assert.deepEqual(events, [
    { event: 'progress', data: '{"kind":"condition_applied"}' },
    { event: 'done', data: '{"reply":"끝"}' },
  ])
})

test('줄과 한글 중간에서 잘려 와도 모아서 하나로 읽는다', () => {
  const text = 'event: reply_delta\ndata: {"text":"예상 인원을 "}\n\n'
  const chunks = [...text].map((c) => c) // 한 글자씩
  assert.deepEqual(parseAll(chunks), [{ event: 'reply_delta', data: '{"text":"예상 인원을 "}' }])
})

test('heartbeat 주석과 CRLF 줄바꿈을 처리한다', () => {
  const events = parseAll([': heartbeat\r\n\r\nevent: done\r\ndata: {}\r\n\r\n'])
  assert.deepEqual(events, [{ event: 'done', data: '{}' }])
})

test('빈 줄 없이 끊긴 마지막 이벤트는 내보내지 않는다', () => {
  const events = parseAll(['event: progress\ndata: {"a":1}\n\nevent: done\ndata: {"b"'])
  assert.deepEqual(events, [{ event: 'progress', data: '{"a":1}' }])
})
