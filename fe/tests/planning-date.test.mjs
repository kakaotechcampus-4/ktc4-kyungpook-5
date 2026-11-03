// Run from fe/: node --test tests/planning-date.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/shared/lib/format.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { formatKstDateInput, formatMonthDay } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
)

test('planning dates display the same Korean calendar day across UTC and +09 representations', () => {
  for (const value of ['2026-12-19T15:00:00Z', '2026-12-20T00:00:00+09:00']) {
    assert.equal(formatKstDateInput(value), '2026-12-20')
    assert.equal(formatMonthDay(value), '12/20')
  }
  assert.equal(formatKstDateInput(null), '')
  assert.equal(formatKstDateInput(undefined), '')
  assert.equal(formatKstDateInput('2026-01-01T00:00:00Z'), '2026-01-01')
})
