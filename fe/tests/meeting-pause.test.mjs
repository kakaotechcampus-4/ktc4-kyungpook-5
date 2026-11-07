// Run from fe/: node --test tests/*.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/features/meetings/audio/pause.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { pausedAt, resumedAt, recordedTime } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
)

test('silence streamed while paused is left out of the recorded time', () => {
  let clock = { durationMs: 60_000, pausedMs: 0, pausedAtMs: null }
  clock = { ...clock, ...pausedAt(clock) }
  clock = { ...clock, durationMs: 90_000 }
  assert.equal(recordedTime(clock), 60_000, 'the timer stops while paused')
  clock = { ...clock, ...resumedAt(clock), durationMs: 100_000 }
  assert.equal(recordedTime(clock), 70_000)
  clock = { ...clock, ...pausedAt(clock), durationMs: 130_000 }
  clock = { ...clock, ...resumedAt(clock), durationMs: 140_000 }
  assert.equal(recordedTime(clock), 80_000, 'a second pause adds up')
  assert.equal(recordedTime({ ...clock, ...resumedAt(clock) }), 80_000, 'resuming twice adds nothing')
})
