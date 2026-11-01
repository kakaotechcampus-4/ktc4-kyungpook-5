import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
const source = await readFile(
  new URL('../src/features/auth/destination.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const exports = {}
vm.runInNewContext(outputText, {
  exports,
  URL,
  window: { location: { origin: 'https://example.test' } },
})
test('default and unsafe destinations go to the dashboard', () => {
  for (const value of [
    null,
    'https://other.test/a',
    '//other.test/a',
    '/login',
    'https://example.test//other.test/path',
    '/auth/kakao/callback?code=x',
    '/signup',
    '/signup?invite=x&other=y',
  ])
    assert.equal(exports.safeDestination(value), '/dashboard')
})
test('safe explicit record, notification and invitation targets are preserved', () => {
  for (const value of ['/records', '/meetings/m1?clubId=c#task', '/signup?invite=valid_token-1'])
    assert.equal(exports.safeDestination(value), value)
})
