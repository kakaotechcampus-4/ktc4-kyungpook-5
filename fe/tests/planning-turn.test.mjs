import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

// turn.ts는 타입만 import하므로 그대로 옮겨 실행한다.
async function load() {
  const source = await readFile(
    new URL('../src/features/planning/turn.ts', import.meta.url),
    'utf8',
  )
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  const exports = {}
  vm.runInNewContext(outputText, { exports })
  return exports
}

const line = (operationId, status, text = operationId) => ({
  operationId,
  kind: 'search_started',
  status,
  text,
})

test('같은 작업의 결과 줄은 제자리에서 바뀌어 줄 순서가 튀지 않는다', async () => {
  const { upsertProgress } = await load()
  let lines = []
  lines = upsertProgress(lines, line('search', 'running', '지난 행사 기록을 찾고 있어요'))
  lines = upsertProgress(lines, line('cond', 'completed', '예상 인원 40명 반영했어요'))
  lines = upsertProgress(lines, line('search', 'completed', '참고할 기록을 찾았어요'))
  assert.deepEqual(
    // vm에서 만든 배열은 프로토타입이 달라 이 쪽 배열로 옮겨 비교한다.
    Array.from(lines, (l) => [l.operationId, l.status]),
    [
      ['search', 'completed'],
      ['cond', 'completed'],
    ],
  )
})

test('한 턴의 작업 줄은 상한까지만 남는다', async () => {
  const { upsertProgress, MAX_TURN_LINES } = await load()
  let lines = []
  for (let i = 0; i < MAX_TURN_LINES + 2; i += 1)
    lines = upsertProgress(lines, line(`op${i}`, 'completed'))
  assert.equal(lines.length, MAX_TURN_LINES)
  assert.equal(lines.at(-1).operationId, `op${MAX_TURN_LINES + 1}`)
})

test('작업 줄은 보낼 때 위치 바로 뒤의 토리 답변에 붙는다', async () => {
  const { attachReceipts } = await load()
  const messages = [
    { id: 'm1', from: '나', text: '다음 달에 MT 가려고 해' },
    { id: 'm2', from: '토리', text: '몇 명 정도 가나요?' },
    { id: 'm3', from: '나', text: '40명' },
    { id: 'm4', from: '토리', text: '40명으로 반영했어요.' },
  ]
  const lines = [line('cond', 'completed', '예상 인원 40명 반영했어요')]
  const result = attachReceipts(messages, [{ base: 2, lines }])
  assert.equal(result[3].receipt, lines)
  assert.equal(result[1].receipt, undefined)
  assert.equal(messages[3].receipt, undefined, '원래 배열은 바꾸지 않는다')
})

test('답변이 저장되지 않은 턴의 작업 줄은 다음 턴 답변에 붙지 않는다', async () => {
  const { attachReceipts } = await load()
  const messages = [
    { id: 'm1', from: '나', text: '인원 40명' },
    { id: 'm2', from: '나', text: '장소는 가평' },
    { id: 'm3', from: '토리', text: '가평으로 반영했어요.' },
  ]
  const result = attachReceipts(messages, [{ base: 0, lines: [line('cond', 'completed')] }])
  assert.deepEqual(
    Array.from(result, (m) => m.receipt),
    [undefined, undefined, undefined],
  )
})
