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

function render(status) {
  return renderToStaticMarkup(React.createElement(EventHeaderCard, {
    event: { id: 'event-1', title: '행사', status, startDate: null, endDate: null,
      location: null, headcount: null, currentStep: null },
    steps: [], onSelectStep() {}, onCancelEvent() {}, onViewCancellation() {},
    onEditPlan() {}, onStartEvent() {}, onCompleteEvent() {},
  }))
}

test('planning offers actionable plan edit and cancellation', () => {
  const html = render('PLANNING')
  assert.match(html, /<button[^>]*>단계 수정<\/button>/)
  assert.match(html, /<button[^>]*>행사 취소<\/button>/)
  const cancelButton = html.match(/<button[^>]*>행사 취소<\/button>/)?.[0]
  assert.doesNotMatch(cancelButton, /\sdisabled(?:\s|=|>)/)
})

test('in-progress events can cancel but cannot edit the planning structure', () => {
  const html = render('ON_GOING')
  assert.match(html, />행사 취소<\/button>/)
  assert.doesNotMatch(html, />단계 수정<\/button>/)
})

test('cancelled states lead back to cleanup rather than starting cancellation twice', () => {
  for (const status of ['CANCELLING', 'CANCELLED']) {
    const html = render(status)
    assert.match(html, />취소 정리 보기<\/button>/)
    assert.doesNotMatch(html, />행사 취소<\/button>/)
  }
  assert.doesNotMatch(render('COMPLETE'), />행사 취소<\/button>/)
})
