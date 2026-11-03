// Run from fe/: node --test tests/operation-cases-api.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(new URL('../src/features/events/operationCasesApi.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } })
function api(client) {
  const exports = {}
  vm.runInNewContext(outputText, { exports, require: () => client })
  return exports
}
test('operation cases follow all pages and encode event/case paths', async () => {
  const calls = []
  const client = {
    apiGetPage: async (path) => { calls.push(path); return path.includes('page=1') ? {data: [{id:'one'}], meta: {totalCount:2}} : {data:[{id:'two'}],meta:{totalCount:2}} },
    apiGet: async (path) => { calls.push(path); return {} },
    apiPost: async (path, body) => { calls.push([path, body]); return {} },
  }
  const a = api(client)
  assert.equal((await a.listOperationCases('event/1')).length, 2)
  await a.getOperationCase('event/1', 'case/2')
  await a.createOperationCase('event/1', {clientRequestId:'request',situation:'장소 변경'})
  await a.retryOperationQuestion('event/1','case/2')
  await a.generateOperationResult('event/1','case/2')
  assert.equal(calls[0], '/events/event%2F1/operation-cases?page=1&size=100')
  assert.equal(calls[1], '/events/event%2F1/operation-cases?page=2&size=100')
  assert.equal(calls[2], '/events/event%2F1/operation-cases/case%2F2')
  assert.equal(calls[3][1].clientRequestId, 'request')
  assert.equal(calls[4][0], '/events/event%2F1/operation-cases/case%2F2/question')
  assert.equal(calls[5][0], '/events/event%2F1/operation-cases/case%2F2/result')
})
test('list failure is propagated instead of presenting partial cases as complete', async () => {
  const a = api({apiGetPage: async (path) => {if (path.includes('page=1')) return {data:[{}],meta:{totalCount:2}}; throw new Error('offline')}})
  await assert.rejects(a.listOperationCases('event'), /offline/)
})
