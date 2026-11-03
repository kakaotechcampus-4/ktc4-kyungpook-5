// Run from fe/: node --test tests/main-entry.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(new URL('../src/pages/MainEntryPage.tsx', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
})
function render(token, query) {
  const exports = {}
  vm.runInNewContext(outputText, {
    exports,
    require: (id) => {
      if (id === 'react/jsx-runtime') return { jsx: (_component, props) => props }
      if (id === '@/features/auth/hooks') return { useMe: () => query }
      if (id === '@/shared/auth/store') return { useAuthStore: (selector) => selector({ token }) }
      if (id === '@/features/home/ServiceHomePage') return { default: () => null }
      throw new Error(`Unexpected import: ${id}`)
    },
  })
  return exports.default()
}

test('public entry selects the service only for a verified session', () => {
  for (const [token, query] of [
    [null, { isSuccess: false }],
    ['test', { isSuccess: false, isPending: true }],
    ['test', { isSuccess: false, isError: true }],
    [null, { isSuccess: true, data: {} }],
  ]) {
    const props = render(token, query)
    assert.equal(props.primaryHref, '/login')
    assert.equal(props.primaryLabel, '운영해 시작하기')
  }
  const verified = render('test', { isSuccess: true, data: { id: 'user' } })
  assert.equal(verified.primaryHref, '/dashboard')
  assert.equal(verified.primaryLabel, '서비스 열기')
})
