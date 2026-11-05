import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { build } from 'esbuild'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dir = await mkdtemp(path.join(root, 'tests/.planning-overview-'))
const output = path.join(dir, 'bundle.mjs')
const built = await build({
  entryPoints: [path.join(root, 'src/features/events/components/PlanningOverview.tsx')],
  bundle: true,
  format: 'esm',
  platform: 'node',
  jsx: 'automatic',
  packages: 'external',
  alias: { '@': path.join(root, 'src') },
  write: false,
})
await writeFile(output, built.outputFiles[0].contents)
const { PlanningOverview } = await import(pathToFileURL(output).href)
await rm(dir, { recursive: true })

const event = (startDate = null, endDate = null) => ({
  id: 'e', title: '봄 MT', status: 'PLANNING', startDate, endDate,
  location: null, headcount: null, currentStep: null,
})
const step = (id, code, name) => ({ id, stepOrder: Number(id), name, code, state: 'TODO', deadline: null })
const render = (ev, steps) =>
  renderToStaticMarkup(React.createElement(PlanningOverview, { event: ev, steps, onContinue() {} }))

test('no draft shows guidance and continue', () => {
  const html = render(event(), [])
  assert.match(html, /아직 계획 초안이 없어요/)
  assert.match(html, />계획 이어보기<\/button>/)
  assert.doesNotMatch(html, /운영 시작 준비/)
})

test('draft is grouped like P2 and keeps server order', () => {
  const html = render(event(), [step('1', 'RESEARCH_VENUE', '장소 조사'), step('2', 'ASSIGN_ROLES', '역할 나누기')])
  assert.match(html, /계획 초안 2단계/)
  assert.match(html, /사전 준비 2/) // 두 code 모두 카탈로그상 '사전 준비'
  assert.ok(html.indexOf('장소 조사') < html.indexOf('역할 나누기'))
})

test('missing start date is marked as needed', () => {
  const html = render(event(), [step('1', 'ASSIGN_ROLES', '역할 나누기')])
  assert.match(html, /행사 시작일 미정/)
  assert.match(html, /필요/)
  assert.match(html, />계획 검토로 가서 운영 시작<\/button>/)
})

test('start date only counts as ready', () => {
  const html = render(event('2026-11-22'), [step('1', 'ASSIGN_ROLES', '역할 나누기')])
  assert.doesNotMatch(html, /행사 시작일 미정/)
  assert.doesNotMatch(html, />필요</)
})

test('steps without code fall into 기타 단계', () => {
  const html = render(event(), [step('1', undefined, '데모 단계')])
  assert.match(html, /기타 단계 1/)
  assert.match(html, /데모 단계/)
})
