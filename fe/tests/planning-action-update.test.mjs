import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
const source = await readFile(
  new URL('../src/features/planning/actionUpdate.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const exports = {}
vm.runInNewContext(outputText, { exports })
const action = { editable: true, version: 3, title: '공지', amount: null, payload: null }
test('unchanged null payload and locked actions produce no update', () => {
  assert.equal(
    exports.buildActionUpdate(action, { title: '공지', amount: null, payload: {} }),
    null,
  )
  assert.equal(
    exports.buildActionUpdate(
      { ...action, editable: false },
      { title: '수정', amount: null, payload: {} },
    ),
    null,
  )
})
test('only edited fields and the observed version are sent', () => {
  const result = exports.buildActionUpdate(
    { ...action, payload: { channel: '단톡', audience: '전체' } },
    { title: '공지', amount: null, payload: { channel: '게시판', audience: '전체' } },
  )
  assert.equal(result.expectedVersion, 3)
  assert.equal(result.payload.channel, '게시판')
  assert.equal(Object.keys(result.payload).length, 1)
  assert.equal('title' in result, false)
  assert.equal('amount' in result, false)
})
