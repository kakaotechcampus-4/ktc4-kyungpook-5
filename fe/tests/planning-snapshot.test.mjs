import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

test('planning snapshot obtains the steps and revision together', async () => {
  const source = await readFile(new URL('../src/features/planning/api.ts', import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  })
  const exports = {}
  const requests = []
  const snapshot = { baseRevision: 8, steps: [{ code: 'ASSIGN_ROLES' }] }
  vm.runInNewContext(outputText, {
    exports,
    require(name) {
      if (name === '@/shared/api/client') return { apiGet: async (url) => { requests.push(url); return snapshot } }
      throw new Error(`Unexpected module: ${name}`)
    },
  })
  assert.equal(await exports.planningApi.stepsSnapshot('event /?'), snapshot)
  assert.deepEqual(requests, ['/events/event%20%2F%3F/plan/steps/snapshot'])
})
