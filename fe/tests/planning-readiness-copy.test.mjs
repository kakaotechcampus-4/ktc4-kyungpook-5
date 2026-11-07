import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/planning/readinessCopy.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const exports = {}
vm.runInNewContext(outputText, { exports })
const { readinessCopy } = exports

test('빠진 항목은 목록 순서대로 한 문장에 모으고, 같은 말을 반복하지 않는다', () => {
  const copy = readinessCopy(['location_unanswered', 'dates_unanswered', 'headcount_unanswered'])
  assert.deepEqual([...copy.needed], ['예상 인원', '일정', '장소'])
  assert.equal(
    copy.text,
    '인원·일정·장소를 정하면 초안을 만들 수 있어요. 아직 모르면 "미정"이라고 답해도 돼요.',
  )
})

test('받침에 따라 조사를 고른다', () => {
  assert.match(readinessCopy(['dates_unanswered']).text, /^일정을 정하면/)
  assert.match(readinessCopy(['location_unanswered']).text, /^장소를 정하면/)
})

test('미정으로 답할 수 없는 행사 종류만 빠졌으면 미정 안내를 붙이지 않는다', () => {
  const copy = readinessCopy(['event_type_missing'])
  assert.deepEqual([...copy.needed], ['종류'])
  assert.equal(copy.text, '행사 종류를 정하면 초안을 만들 수 있어요.')
})

test('목록과 이어지지 않는 이유는 문장만 덧붙이고, 모르는 이유는 한 번만 안내한다', () => {
  const copy = readinessCopy(['condition_change_pending', 'future_a', 'future_b'])
  assert.deepEqual([...copy.needed], [])
  assert.equal(
    copy.text,
    '반영하지 못한 조건 변경을 먼저 확인해 주세요. 추가 정보를 확인해 주세요.',
  )
})

test('이유가 없으면 대화를 이어 가라고 안내한다', () => {
  assert.equal(readinessCopy([]).text, '대화를 이어서 필요한 정보를 확인해 주세요.')
})
