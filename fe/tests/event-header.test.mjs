import assert from 'node:assert/strict'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { build } from 'esbuild'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dir = await mkdtemp(path.join(root, 'tests/.event-header-'))
const output = path.join(dir, 'bundle.mjs')
const built = await build({
  entryPoints: [path.join(root, 'src/features/events/components/EventHeaderCard.tsx')],
  bundle: true,
  format: 'esm',
  platform: 'node',
  jsx: 'automatic',
  packages: 'external',
  alias: { '@': path.join(root, 'src') },
  write: false,
})
await writeFile(output, built.outputFiles[0].contents)
const { EventHeaderCard } = await import(pathToFileURL(output).href)
await rm(dir, { recursive: true })

function render(status, steps = []) {
  return renderToStaticMarkup(React.createElement(EventHeaderCard, {
    event: { id: 'event-1', title: '행사', status, startDate: null, endDate: null,
      location: null, headcount: null, currentStep: null },
    steps, onSelectStep() {}, onCancelEvent() {}, onViewCancellation() {},
    onEditPlan() {}, onStartEvent() {}, onCompleteEvent() {},
  }))
}

// #336 전 서버처럼 계획 중인데도 첫 단계가 CURRENT로 온다.
const steps = [
  { id: 's1', stepOrder: 1, name: '사전 수요 조사', state: 'CURRENT', deadline: null },
  { id: 's2', stepOrder: 2, name: '참가 신청', state: 'TODO', deadline: null },
]

test('planning header ignores step states', () => {
  const html = render('PLANNING', steps)
  assert.doesNotMatch(html, /단계 진행/)
  assert.doesNotMatch(html, /현재 단계/)
  assert.doesNotMatch(html, />행사 시작<\/button>/)
})

test('planning header leads with continuing the plan', () => {
  const first = render('PLANNING', steps).match(/<button[^>]*>[^<]*<\/button>/)[0]
  assert.match(first, />계획 이어보기</)
  assert.match(first, /bg-blue-600/)
})

test('on-going header keeps progress', () => {
  const html = render('ON_GOING', steps)
  assert.match(html, /단계 진행/)
  assert.match(html, />행사 완료<\/button>/)
})

// 취소 정리(안내·예약 취소·환불·기록)는 운영을 시작한 뒤에야 할 일이 생긴다(#381).
// 계획 중에는 「계획 이어보기」만 누를 수 있고 「행사 취소」는 보이지 않는다.
test('planning offers plan edit without cancellation', () => {
  const html = render('PLANNING')
  const editButton = html.match(/<button[^>]*>계획 이어보기<\/button>/)?.[0]
  assert.ok(editButton)
  assert.doesNotMatch(editButton, /\sdisabled(?:\s|=|>)/)
  assert.doesNotMatch(html, />행사 취소<\/button>/)
})

test('in-progress events can cancel but cannot edit the planning structure', () => {
  const html = render('ON_GOING')
  assert.match(html, />행사 취소<\/button>/)
  assert.doesNotMatch(html, />계획 이어보기<\/button>/)
})

test('cancelled states lead back to cleanup rather than starting cancellation twice', () => {
  for (const status of ['CANCELLING', 'CANCELLED']) {
    const html = render(status)
    assert.match(html, />취소 정리 보기<\/button>/)
    assert.doesNotMatch(html, />행사 취소<\/button>/)
  }
  assert.doesNotMatch(render('COMPLETE'), />행사 취소<\/button>/)
})
