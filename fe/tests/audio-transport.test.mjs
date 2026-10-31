// Run from fe/: node --test tests/audio-transport.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const compile = async (path) =>
  ts.transpileModule(await readFile(new URL(path, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
const pcm = {}
vm.runInNewContext(await compile('../src/features/meetings/audio/pcm.ts'), { exports: pcm })
const code = await compile('../src/features/meetings/audio/transport.ts')
function setup() {
  let socket
  const observed = { gaps: [], failures: [], processing: 0, transcripts: 0 }
  class Socket {
    static OPEN = 1
    readyState = 1
    bufferedAmount = 0
    sent = []
    constructor() {
      socket = this
    }
    send(value) {
      this.sent.push(value)
    }
    close() {
      this.readyState = 3
    }
    event(value) {
      this.onmessage({ data: JSON.stringify(value) })
    }
  }
  const exports = {}
  vm.runInNewContext(code, {
    exports,
    URL,
    setTimeout,
    clearTimeout,
    WebSocket: Socket,
    window: { location: { href: 'http://localhost:5173/' } },
    require: (id) =>
      id === './pcm'
        ? pcm
        : {
            getAccessToken: () => 'test',
            getApiBaseUrl: () => 'http://localhost:8000',
          },
  })
  const transport = new exports.MeetingAudioTransport('meeting', {
    onProgress: () => {},
    onGap: (x) => observed.gaps.push([x.startMs, x.endMs]),
    onFailure: (x) => observed.failures.push(x.message),
    onProcessing: () => observed.processing++,
    onTranscript: () => observed.transcripts++,
    onWarning: () => {},
  })
  const ready = transport.connect()
  socket.onopen()
  socket.event({
    type: 'audio.ready',
    format: 'pcm_s16le',
    sampleRate: 16000,
    channels: 1,
    streamOffsetMs: 5000,
  })
  return { socket, transport, ready, observed }
}

test('metadata and final tail precede acknowledgement and completion', async () => {
  const { socket, transport, ready, observed } = setup()
  await ready
  transport.sendFrame(new ArrayBuffer(3200))
  transport.sendFrame(new ArrayBuffer(32))
  const done = transport.end()
  assert.deepEqual(JSON.parse(socket.sent[1]), {
    type: 'audio',
    audioSeq: 1,
    startMs: 0,
    endMs: 100,
  })
  assert.deepEqual(JSON.parse(socket.sent[3]), {
    type: 'audio',
    audioSeq: 2,
    startMs: 100,
    endMs: 101,
  })
  assert.deepEqual(JSON.parse(socket.sent[5]), { type: 'end', lastAudioSeq: 2 })
  socket.event({ type: 'audio.end_ack', lastAudioSeq: 2, status: 'FINALIZING' })
  assert.equal(observed.processing, 1)
  socket.event({ type: 'transcript.final' })
  socket.event({ type: 'audio.completed', lastAudioSeq: 2, status: 'COMPLETED', errorCount: 0 })
  await done
  assert.equal(observed.transcripts, 1)
  assert.equal(observed.failures.length, 0)
})

test('missing ack or mismatched last sequence cannot complete successfully', async () => {
  for (const event of [
    { type: 'audio.completed', lastAudioSeq: 1, status: 'COMPLETED', errorCount: 0 },
    { type: 'audio.end_ack', lastAudioSeq: 0, status: 'FINALIZING' },
  ]) {
    const { socket, transport, ready, observed } = setup()
    await ready
    transport.sendFrame(new ArrayBuffer(3200))
    const done = transport.end()
    socket.event(event)
    await assert.rejects(done)
    assert.equal(observed.failures.length, 1)
  }
})

test('failure and empty transcript gap events retain meeting-relative time', async () => {
  const { socket, transport, ready, observed } = setup()
  await ready
  socket.event({ type: 'audio.error', code: 'STT_FAILED', startMs: 5100, endMs: 5300 })
  socket.event({ type: 'audio.no_transcript', startMs: 5100, endMs: 5300 })
  assert.deepEqual(observed.gaps, [
    [5100, 5300],
    [5100, 5300],
  ])
  transport.dispose()
})

test('failed completion remains an error and refreshes no successful completion', async () => {
  const { socket, transport, ready, observed } = setup()
  await ready
  transport.sendFrame(new ArrayBuffer(3200))
  const done = transport.end()
  socket.event({ type: 'audio.end_ack', lastAudioSeq: 1, status: 'FINALIZING' })
  socket.event({ type: 'audio.completed', lastAudioSeq: 1, status: 'FAILED', errorCount: 1 })
  await assert.rejects(done)
  assert.equal(observed.failures.length, 1)
})

test('unsupported resume guides the user to a new meeting', async () => {
  const { socket, transport, ready, observed } = setup()
  await ready
  socket.event({ type: 'audio.error', code: 'AUDIO_RESUME_UNSUPPORTED' })
  assert.match(observed.failures[0], /새 회의/)
  transport.dispose()
})
