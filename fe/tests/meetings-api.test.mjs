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

test('accepting a candidate saves user edits then accepts the returned version without reserving', async () => {
  const calls = []
  const candidate = { id: 'candidate /?', version: 4 }
  const fields = {
    title: '검토한 후보',
    description: '수정한 메모',
    dueDate: '2026-11-10',
    suggestedAssignee: '운영진',
  }
  const saved = { ...candidate, ...fields, version: 5 }
  const accepted = { ...saved, status: 'ACCEPTED', version: 6 }
  const api = setup({
    apiPatch: async (path, body) => {
      calls.push({ method: 'PATCH', path, body: { ...body } })
      return saved
    },
    apiPost: async (path, body) => {
      calls.push({ method: 'POST', path, body: { ...body } })
      return accepted
    },
  })

  const result = await api.meetingsApi.acceptSuggestion('club /?', candidate, fields)

  assert.equal(result, accepted)
  assert.deepEqual(calls, [
    {
      method: 'PATCH',
      path: '/clubs/club%20%2F%3F/task-suggestions/candidate%20%2F%3F',
      body: { expectedVersion: 4, ...fields },
    },
    {
      method: 'POST',
      path: '/clubs/club%20%2F%3F/task-suggestions/candidate%20%2F%3F/accept',
      body: { expectedVersion: 5 },
    },
  ])
})

test('a failed candidate save prevents accepting the old candidate', async () => {
  const conflict = new Error('candidate write conflict')
  let acceptCalls = 0
  const api = setup({
    apiPatch: async () => { throw conflict },
    apiPost: async () => { acceptCalls += 1 },
  })

  await assert.rejects(
    () => api.meetingsApi.acceptSuggestion('club', { id: 'candidate', version: 4 }, {
      title: '수정한 후보', description: '', dueDate: null, suggestedAssignee: null,
    }),
    (error) => error === conflict,
  )
  assert.equal(acceptCalls, 0)
})

test('confirmation failure after saving stays visible to the caller', async () => {
  const api = setup({
    apiPatch: async () => ({ id: 'candidate', version: 2 }),
    apiPost: async () => { throw new Error('confirmation unavailable') },
  })
  await assert.rejects(
    api.meetingsApi.acceptSuggestion('club', { id: 'candidate', version: 1 }, { title: '후보' }),
    /confirmation unavailable/,
  )
})
