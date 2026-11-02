import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'
const source = await readFile(new URL('../src/features/meetings/audio/rnnoiseStream.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const { RnnoiseStream } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

test('arbitrary chunks including short tail preserve all samples after a one-frame model delay', () => {
  for (const size of [0, 1, 127, 479, 480, 481, 960, 1664, 10003]) {
    const original = Float32Array.from({length:size},(_, i)=>(i%71-35)/80)
    let last = new Float32Array(480), destroyed = false
    const fake = {processFrame(frame) {let next = frame.slice();frame.set(last);last=next;return 0}, destroy(){destroyed=true}}
    const parts=[]; const stream=new RnnoiseStream(fake,(chunk)=>parts.push(...chunk))
    for(let i=0;i<size;i+=127) stream.push(original.subarray(i,i+127))
    stream.finish()
    const tail = size ? 480 * 6 : 0
    assert.equal(parts.length, size + tail, `size ${size}`)
    assert.deepEqual(parts.slice(0, size), Array.from(original), `alignment ${size}`)
    assert.ok(parts.slice(size).every((value) => value === 0), `tail ${size}`)
    assert.equal(destroyed,true)
  }
})

test('flush retains a delayed signal in the appended filter tail', () => {
  let previous = new Float32Array(480)
  let older = new Float32Array(480)
  const fake = {
    processFrame(frame) {
      const next = frame.slice()
      frame.set(older)
      older = previous
      previous = next
      return 0
    },
    destroy() {},
  }
  const parts = []
  const stream = new RnnoiseStream(fake, (chunk) => parts.push(...chunk))
  stream.push(new Float32Array(480).fill(0.25))
  stream.finish()
  assert.equal(parts.length, 480 * 7)
  assert.ok(parts.slice(0, 480).every((sample) => sample === 0))
  assert.ok(parts.slice(480, 960).every((sample) => sample === 0.25))
})
