import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(new URL('../src/features/planning/api.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
function setup(client) {
  const exports = {}
  vm.runInNewContext(outputText, {
    exports,
    require: (name) => {
      if (name === '@/shared/api/client') return client
      throw new Error(`Unexpected module: ${name}`)
    },
  })
  return exports.planningApi
}
test('step composition, action version and event transitions use the agreed routes', async () => {
  const calls = []
  const api = setup({
    apiPatch: async (...args) => calls.push(['PATCH', ...args]),
    apiPost: async (...args) => calls.push(['POST', ...args]),
  })
  await api.saveSteps('event /', ['ASSIGN_ROLES'])
  await api.updateAction('action /', { expectedVersion: 7, title: '검토' })
  await api.start('event /')
  await api.complete('event /')
  assert.equal(calls[0][1], '/events/event%20%2F/plan/steps')
  assert.deepEqual(Array.from(calls[0][2].codes), ['ASSIGN_ROLES'])
  assert.equal(calls[1][1], '/actions/action%20%2F')
  assert.equal(calls[1][2].expectedVersion, 7)
  assert.equal(calls[2][1], '/events/event%20%2F/start')
  assert.equal(calls[3][1], '/events/event%20%2F/complete')
})
test('server conflict is surfaced to the caller', async () => {
  const api = setup({
    apiPatch: async () => {
      throw new Error('VERSION_CONFLICT')
    },
  })
  await assert.rejects(api.updateAction('a', { expectedVersion: 1 }), /VERSION_CONFLICT/)
})

test('replacement permission is carried only in the explicit generation request', async () => {
  const calls = []
  const api = setup({ apiPost: async (path, body) => calls.push({ path, body }) })
  await api.generate('event', {
    baseRevision: 2,
    useCurrentConditions: false,
    replaceEditedPlan: false,
  })
  await api.generate('event', {
    baseRevision: 2,
    useCurrentConditions: false,
    replaceEditedPlan: true,
  })
  assert.equal(calls[0].path, '/events/event/plan/generate')
  assert.equal(calls[0].body.replaceEditedPlan, false)
  assert.equal(calls[1].body.replaceEditedPlan, true)
  assert.equal(calls[1].body.useCurrentConditions, false)
})
