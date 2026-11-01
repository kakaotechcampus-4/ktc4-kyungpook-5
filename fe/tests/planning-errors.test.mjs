import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const typesSource = await readFile(new URL('../src/shared/api/types.ts', import.meta.url), 'utf8')
const errorsSource = await readFile(new URL('../src/features/planning/errors.ts', import.meta.url), 'utf8')

function transpile(source) {
  return ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
}

const typeExports = {}
vm.runInNewContext(transpile(typesSource), { exports: typeExports })
const errorExports = {}
vm.runInNewContext(transpile(errorsSource), {
  exports: errorExports,
  require: (name) => {
    if (name === '@/shared/api/types') return typeExports
    throw new Error(`Unexpected module: ${name}`)
  },
})

test('partial planning saves explain what was already written', () => {
  const error = new errorExports.PartialPlanSaveError(['일정', "작업 '장소 예약'"], 2)
  assert.match(error.message, /일정 · 작업 '장소 예약'은 저장됐어요/)
  assert.match(error.message, /저장하지 못한 항목 2건/)
  assert.match(errorExports.planningError(error), /최신 계획을 다시 불러온 뒤 다시 시도해 주세요/)
})

test('planning conflict errors ask for a fresh read', () => {
  const error = new typeExports.ApiError({
    code: 'VERSION_CONFLICT',
    message: 'server message',
  })
  assert.equal(
    errorExports.planningError(error),
    '다른 변경이 있어요. 최신 계획을 다시 불러온 뒤 다시 시도해 주세요.',
  )
})
