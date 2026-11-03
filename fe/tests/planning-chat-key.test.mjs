import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/planning/chatKey.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const exports = {}
vm.runInNewContext(outputText, { exports })
const key = {
  key: 'Enter',
  shiftKey: false,
  altKey: false,
  ctrlKey: false,
  metaKey: false,
  isComposing: false,
  keyCode: 13,
}

test('Enter sends, while newline, IME confirmation and modified keys do not', () => {
  assert.equal(exports.isSendKey(key), true)
  for (const change of [
    { shiftKey: true },
    { isComposing: true },
    { keyCode: 229 },
    { key: 'a' },
    { altKey: true },
    { ctrlKey: true },
    { metaKey: true },
  ]) {
    assert.equal(exports.isSendKey({ ...key, ...change }), false)
  }
})
