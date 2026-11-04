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

test('조건 반영 시작 줄은 같은 자리에서 완료 줄로 바뀐다', async () => {
  const { upsertProgress, finishedLines } = await load()
  let lines = []
  lines = upsertProgress(lines, {
    ...line('c1', 'running', '조건을 반영하고 있어요'),
    kind: 'condition_started',
  })
  lines = upsertProgress(lines, line('s1', 'running', '지난 행사 기록을 찾고 있어요'))
  lines = upsertProgress(lines, {
    ...line('c1', 'completed', "행사 이름 '2026년 MT' 반영했어요"),
    kind: 'condition_applied',
  })
  assert.deepEqual(
    Array.from(lines, (l) => [l.operationId, l.status]),
    [
      ['c1', 'completed'],
      ['s1', 'running'],
    ],
  )
  // 답변 위에 남기는 줄은 끝난 것만이다.
  assert.deepEqual(
    Array.from(finishedLines(lines), (l) => l.operationId),
    ['c1'],
  )
})

test('거절·같은 값(skipped)은 답변이 시작될 때까지 진행 중 문구로 남고, 지울 줄이 없으면 붙이지 않는다', async () => {
  const { upsertProgress, dropSkipped, finishedLines } = await load()
  let lines = [line('c1', 'running', '조건을 반영하고 있어요'), line('s1', 'completed')]
  lines = upsertProgress(lines, line('c1', 'skipped', '바뀐 조건이 없어요'))
  // 다시 시도될 수 있어 같은 자리에 진행 중 문구로 남는다. 답변 위에는 남기지 않는다.
  assert.deepEqual(
    Array.from(lines, (l) => [l.operationId, l.status, l.text]),
    [
      ['c1', 'skipped', '조건을 반영하고 있어요'],
      ['s1', 'completed', 's1'],
    ],
  )
  assert.deepEqual(
    Array.from(finishedLines(lines), (l) => l.operationId),
    ['s1'],
  )
  // 답변이 시작되면 뺀다.
  assert.deepEqual(
    Array.from(dropSkipped(lines), (l) => l.operationId),
    ['s1'],
  )
  // 재접속으로 줄을 비운 뒤 온 skipped는 무시한다.
  assert.deepEqual(
    Array.from(upsertProgress([], line('c9', 'skipped')), (l) => l.operationId),
    [],
  )
})

test('거절된 조건을 다시 시도하면 처음 줄의 자리를 이어 써서 사라졌다 다시 생기지 않는다', async () => {
  const { upsertProgress, finishedLines } = await load()
  const cond = (id, status, text) => ({ ...line(id, status, text), kind: 'condition_started' })
  // "…참가비는 20000원" → [검색, 참가비 변경] → 참가비 거절 → 다시 [참가비 변경] → 반영
  let lines = []
  lines = upsertProgress(lines, line('s1', 'running', '지난 행사 기록을 찾고 있어요'))
  lines = upsertProgress(lines, cond('c1', 'running', '조건을 반영하고 있어요'))
  lines = upsertProgress(lines, line('s1', 'empty', '맞는 기록이 없었어요'))
  lines = upsertProgress(lines, {
    ...line('c1', 'skipped', '바뀐 조건이 없어요'),
    kind: 'condition_applied',
  })
  lines = upsertProgress(lines, cond('c2', 'running', '조건을 반영하고 있어요'))
  lines = upsertProgress(lines, {
    ...line('c2', 'completed', '참가비 1인 20,000원 반영했어요'),
    kind: 'condition_applied',
  })
  // 두 번째 시도는 c2지만 화면의 자리(slot)는 처음 줄 c1 그대로다.
  assert.deepEqual(
    Array.from(lines, (l) => [l.slot ?? l.operationId, l.operationId, l.status]),
    [
      ['s1', 's1', 'empty'],
      ['c1', 'c2', 'completed'],
    ],
  )
  assert.deepEqual(
    Array.from(finishedLines(lines), (l) => l.text),
    ['맞는 기록이 없었어요', '참가비 1인 20,000원 반영했어요'],
  )
})

test('기록 없음(empty) 줄은 실패가 아니라 끝난 작업으로 답변 위에 남는다', async () => {
  const { upsertProgress, finishedLines } = await load()
  let lines = upsertProgress([], line('s1', 'running', '지난 행사 기록을 찾고 있어요'))
  lines = upsertProgress(lines, line('s1', 'empty', '맞는 기록이 없었어요'))
  assert.deepEqual(
    Array.from(finishedLines(lines), (item) => [item.status, item.text]),
    [['empty', '맞는 기록이 없었어요']],
  )
})
