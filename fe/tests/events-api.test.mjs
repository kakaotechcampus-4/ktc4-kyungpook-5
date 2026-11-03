import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(new URL('../src/features/events/api.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
function setup(client) {
  const exports = {}
  vm.runInNewContext(outputText, {
    exports,
    URLSearchParams,
    require: (name) => {
      if (name === '@/shared/api/client') return client
      throw new Error(`Unexpected module: ${name}`)
    },
  })
  return exports
}
test('event list requests the selected club and follows every server page', async () => {
  const requests = []
  const api = setup({
    apiGetPage: async (path) => {
      const params = new URLSearchParams(path.split('?')[1])
      requests.push(params)
      return {
        data: params.get('page') === '1' ? [{ id: 'one' }] : [{ id: 'two' }],
        meta: { totalCount: 2 },
      }
    },
  })
  const results = await api.getEvents('club & a', 'ON_GOING')
  assert.deepEqual(
    Array.from(results, (item) => item.id),
    ['one', 'two'],
  )
  assert.equal(requests.length, 2)
  assert.equal(requests[0].get('clubId'), 'club & a')
  assert.equal(requests[0].get('status'), 'ON_GOING')
  assert.equal(requests[0].get('size'), '100')
  assert.equal(requests[1].get('page'), '2')
})
test('a later page failure is propagated rather than returned as partial success', async () => {
  let calls = 0
  const api = setup({
    apiGetPage: async () => {
      if (++calls === 2) throw new Error('server failure')
      return { data: [{ id: 'one' }], meta: { totalCount: 2 } }
    },
  })
  await assert.rejects(api.getEvents('club'), /server failure/)
})
test('action queries encode event identifiers and preserve filters', async () => {
  let url
  const api = setup({
    apiGetPage: async (path) => {
      url = path
      return { data: [], meta: { totalCount: 0 } }
    },
  })
  await api.getEventActions('id /?', 'status=PENDING&type=CONFIRMATION')
  assert.match(url, /^\/events\/id%20%2F%3F\/actions\?/)
  const params = new URLSearchParams(url.split('?')[1])
  assert.equal(params.get('status'), 'PENDING')
  assert.equal(params.get('type'), 'CONFIRMATION')
})

test('detail and step reads encode the event id', async () => {
  const requests = []
  const api = setup({
    apiGet: async (path) => {
      requests.push(path)
      return { id: 'event-1' }
    },
  })
  await api.getEventDetail('event /?')
  await api.getEventSteps('event /?')
  assert.deepEqual(requests, ['/events/event%20%2F%3F', '/events/event%20%2F%3F/steps'])
})

test('action page keeps the server total and falls back to the item count', async () => {
  const paths = []
  const api = setup({
    apiGetPage: async (path) => {
      paths.push(path)
      return { data: [{ id: 'action-1' }], meta: { totalCount: 7 } }
    },
  })
  const page = await api.getEventActionPage('event-1', 'status=DONE&size=3')
  assert.equal(page.totalCount, 7)
  assert.equal(page.items.length, 1)
  assert.equal(page.items[0].id, 'action-1')
  assert.equal(paths[0], '/events/event-1/actions?status=DONE&size=3')

  const fallback = setup({
    apiGetPage: async () => ({ data: [{ id: 'action-1' }, { id: 'action-2' }], meta: null }),
  })
  const fallbackPage = await fallback.getEventActionPage('event-1', '')
  assert.equal(fallbackPage.totalCount, 2)
  assert.deepEqual(Array.from(fallbackPage.items, (item) => item.id), ['action-1', 'action-2'])
})
