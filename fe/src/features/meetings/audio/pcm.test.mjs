// Run: node --experimental-transform-types --test src/features/meetings/audio/pcm.test.mjs
import assert from 'node:assert/strict'
import test from 'node:test'
import { PcmFramer, PcmFrameClock } from './pcm.ts'

function encode(input, sampleRate, chunkSize) {
  const frames = []
  const framer = new PcmFramer(sampleRate, (frame) => frames.push(Buffer.from(frame)))
  for (let offset = 0; offset < input.length; offset += chunkSize) {
    framer.push(input.subarray(offset, offset + chunkSize))
  }
  framer.flush()
  return frames
}

test('48 kHz continuous capture yields exactly 16,000 samples per second', () => {
  const frames = encode(new Float32Array(48_000).fill(0.5), 48_000, 127)
  assert.equal(frames.length, 10)
  assert.ok(frames.every((frame) => frame.byteLength === 3200))
  const pcm = Buffer.concat(frames)
  for (let offset = 0; offset < pcm.length; offset += 2)
    assert.equal(pcm.readInt16LE(offset), 16384)
})

test('44.1 kHz chunk boundaries preserve output order and the partial tail', () => {
  const samples = Float32Array.from({ length: 44_137 }, (_, index) => Math.sin(index / 20))
  const whole = Buffer.concat(encode(samples, 44_100, samples.length))
  const chunked = Buffer.concat(encode(samples, 44_100, 128))
  assert.deepEqual(chunked, whole)
  assert.equal(
    chunked.byteLength,
    Math.ceil(Math.ceil((samples.length * 16_000) / 44_100) / 16) * 32,
  )
})

test('PCM is signed little endian and clips invalid/out-of-range samples', () => {
  const pcm = Buffer.concat(encode(new Float32Array([-2, -1, 0, 0.5, 1, 2, NaN]), 16_000, 3))
  assert.deepEqual(
    Array.from({ length: 7 }, (_, index) => pcm.readInt16LE(index * 2)),
    [-32768, -32768, 0, 16384, 32767, 32767, 0],
  )
})

test('tail flush emits a short final frame once, without dropping silence', () => {
  const frames = []
  const framer = new PcmFramer(16_000, (frame) => frames.push(frame))
  framer.push(new Float32Array(1599))
  assert.equal(frames.length, 0)
  framer.flush()
  framer.flush()
  framer.push(new Float32Array(1))
  assert.equal(frames.length, 1)
  assert.equal(frames[0].byteLength, 3200)
  assert.ok(new Uint8Array(frames[0]).every((byte) => byte === 0))
})

test('audio sequence and integer timestamps follow samples, including the last tail', () => {
  const clock = new PcmFrameClock()
  assert.deepEqual(clock.next(3200), { type: 'audio', audioSeq: 1, startMs: 0, endMs: 100 })
  assert.deepEqual(clock.next(3200), { type: 'audio', audioSeq: 2, startMs: 100, endMs: 200 })
  assert.deepEqual(clock.next(640), { type: 'audio', audioSeq: 3, startMs: 200, endMs: 220 })
  assert.equal(clock.durationMs, 220)
  assert.throws(() => clock.next(0))
  assert.throws(() => clock.next(3))
  assert.throws(() => clock.next(638))
})
