import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(new URL('../src/features/meetings/api.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})

function setup(client) {
  const exports = {}
  vm.runInNewContext(outputText, {
    exports,
    URLSearchParams,
    encodeURIComponent,
    require: (name) => {
      if (name === '@/shared/api/client') return client
      throw new Error(`Unexpected module: ${name}`)
    },
  })
  return exports
}

test('meeting list scopes the request to the selected club', async () => {
  let path
  const api = setup({
    apiGetPage: async (value) => {
      path = value
      return { data: [], meta: { page: 1, size: 100, totalCount: 0 } }
    },
  })
  const result = await api.meetingsApi.list('club /?', 'COMPLETED')
  const params = new URLSearchParams(path.split('?')[1])
  assert.equal(path.split('?')[0], '/clubs/club%20%2F%3F/meetings')
  assert.equal(params.get('status'), 'COMPLETED')
  assert.equal(params.get('size'), '100')
  assert.deepEqual(Array.from(result.data), [])
})
