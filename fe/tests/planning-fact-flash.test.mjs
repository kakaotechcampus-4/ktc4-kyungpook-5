// Run from fe/: node --test tests/planning-fact-flash.test.mjs
// 조건 패널의 바뀐 칸 강조(#300). factFlash.ts는 타입만 import하므로 그대로 옮겨 실행한다.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/planning/factFlash.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { changedFacts, flashLeft, FACT_FLASH_MS } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
)

test('값이나 상태가 달라진 칸만 강조하고, 근거 발화만 바뀐 칸은 두지 않는다', () => {
  const before = {
    '예상 인원': { status: '확정', value: '30' },
    참가비: { status: '잠정', value: '20000', quote: '2만 원 정도?' },
    장소: { status: '확정', value: '가평' },
  }
  const after = {
    '예상 인원': { status: '확정', value: '40' }, // 값 바뀜
    참가비: { status: '잠정', value: '20000', quote: '2만 원쯤' }, // 근거 발화만 바뀜
    장소: { status: '확정', value: '가평' }, // 그대로
    일정: { status: '확정', value: '12/5 – 12/6' }, // 미정 → 정함
  }
  assert.deepEqual(changedFacts(before, after).sort(), ['예상 인원', '일정'].sort())
  // 잠정 → 확정처럼 상태만 바뀌어도 강조한다. 값을 지워 미정이 된 칸도 강조한다.
  assert.deepEqual(
    changedFacts(
      { 참가비: { status: '잠정', value: '20000' }, 장소: { status: '확정', value: '가평' } },
      { 참가비: { status: '확정', value: '20000' } },
    ).sort(),
    ['장소', '참가비'].sort(),
  )
  assert.deepEqual(changedFacts(after, after), [])
})

test('강조는 조건 완료 순간부터 정해진 시간 동안만 켜지고, 다시 그려도 지난 강조는 켜지지 않는다', () => {
  const flash = { at: 1000, keys: ['예상 인원'] }
  assert.equal(flashLeft(flash, 1000), FACT_FLASH_MS)
  assert.equal(flashLeft(flash, 1000 + FACT_FLASH_MS - 100), 100)
  assert.equal(flashLeft(flash, 1000 + FACT_FLASH_MS + 5000), 0)
  assert.equal(flashLeft({ at: 1000, keys: [] }, 1000), 0)
  assert.equal(flashLeft(null, 1000), 0)
})
