import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { build } from 'esbuild'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const { outputFiles } = await build({
  entryPoints: [path.join(root, 'src/shared/lib/demo.ts')],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'esm',
})
const { demoNavigationPath, supportsDemoPath } = await import(
  `data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`,
)

test('demo navigation removes only the demo flag and preserves the route context', () => {
  assert.equal(
    demoNavigationPath('/planning', '?demo&eventId=event%201', '#facts'),
    '/planning?eventId=event+1#facts',
  )
})

test('routes without the demo flag do not create a real-service link', () => {
  assert.equal(demoNavigationPath('/dashboard', '?clubId=club-1'), null)
})

test('demo mode is limited to screens that actually use example data', () => {
  assert.equal(supportsDemoPath('/planning/steps'), true)
  assert.equal(supportsDemoPath('/events/event-1'), true)
  assert.equal(supportsDemoPath('/dashboard'), false)
})
