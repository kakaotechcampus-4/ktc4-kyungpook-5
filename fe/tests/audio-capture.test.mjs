import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = (await readFile(new URL('../src/features/meetings/audio/capture.ts', import.meta.url), 'utf8'))
  .replace('import.meta.env.BASE_URL', "'/'")
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText

async function setup(settings) {
  let constraints
  let time = 0
  let processor
  let stopped = false
  const sent = []
  const levels = []
  const track = { getSettings: () => settings, stop: () => { stopped = true }, onended: null }
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] }
  class Framer {
    push(samples) { sent.push(Array.from(samples)) }
    flush() {}
  }
  class Worklet {
    constructor() { processor = this; this.port = { close() {}, postMessage() {} } }
    connect() {}
    disconnect() {}
  }
  class AudioContextMock {
    state = 'running'
    sampleRate = 16000
    destination = {}
    audioWorklet = { addModule: async () => {} }
    createMediaStreamSource() { return { connect() {}, disconnect() {} } }
    createGain() { return { gain: {}, connect() {}, disconnect() {} } }
    async resume() {}
    async close() { this.state = 'closed' }
  }
  const exports = {}
  vm.runInNewContext(code, {
    exports, require: () => ({ PcmFramer: Framer }),
    window: { isSecureContext: true, AudioContext: AudioContextMock, AudioWorkletNode: Worklet },
    navigator: { mediaDevices: { getUserMedia: async (value) => { constraints = value; return stream } } },
    AudioContext: AudioContextMock, AudioWorkletNode: Worklet,
    Float32Array, performance: { now: () => time }, setTimeout, clearTimeout,
  })
  const capture = await exports.startPcmCapture(() => {}, (error) => { throw error }, (level) => levels.push(level))
  return {
    capture, constraints, sent, levels,
    feed(samples) { time += 100; processor.port.onmessage({ data: { type: 'samples', samples } }) },
    isStopped: () => stopped,
  }
}

test('meter is smoothed without altering audio and reports browser suppression setting', async () => {
  const m = await setup({ noiseSuppression: false })
  assert.equal(m.constraints.audio.noiseSuppression, true)
  assert.equal(m.capture.noiseSuppression, false)
  const voice = new Float32Array([0.1, 0.1])
  const quiet = new Float32Array([0, 0])
  m.feed(voice)
  m.feed(quiet)
  assert.ok(Math.abs(m.levels[0] - 0.32) < 0.001)
  assert.ok(Math.abs(m.levels[1] - 0.256) < 0.001)
  assert.deepEqual(m.sent, [Array.from(voice), Array.from(quiet)])
  m.capture.cancel()
  assert.equal(m.isStopped(), true)
})

test('unknown suppression support is not reported as enabled or disabled', async () => {
  const m = await setup({})
  assert.equal(m.capture.noiseSuppression, undefined)
  m.capture.cancel()
})
