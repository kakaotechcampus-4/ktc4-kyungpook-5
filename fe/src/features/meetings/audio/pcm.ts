export const PCM_SAMPLE_RATE = 16_000
export const PCM_FRAME_SAMPLES = 1_600

export class PcmFrameClock {
  private sequence = 0
  private samples = 0

  get durationMs() {
    return Math.round((this.samples * 1000) / PCM_SAMPLE_RATE)
  }

  next(byteLength: number) {
    if (!Number.isInteger(byteLength) || byteLength <= 0 || byteLength % 32 !== 0) {
      throw new Error('음성 데이터 형식이 올바르지 않아요.')
    }
    const startMs = this.durationMs
    this.samples += byteLength / 2
    return { type: 'audio' as const, audioSeq: ++this.sequence, startMs, endMs: this.durationMs }
  }
}

// A weighted average spans input chunks, so 44.1/48 kHz boundaries never restart
// the resampling clock. There is no speech/silence judgment in the client.
export class PcmFramer {
  private readonly ratio: number
  private remaining: number
  private sum = 0
  private weight = 0
  private frame = new Int16Array(PCM_FRAME_SAMPLES)
  private length = 0
  private closed = false

  constructor(
    inputRate: number,
    private readonly emit: (pcm: ArrayBuffer) => void,
  ) {
    if (!Number.isFinite(inputRate) || inputRate <= 0) throw new Error('Invalid sample rate')
    this.ratio = inputRate / PCM_SAMPLE_RATE
    this.remaining = this.ratio
  }

  push(samples: Float32Array) {
    if (this.closed) return
    for (const value of samples) {
      let available = 1
      while (available > 1e-9) {
        const contribution = Math.min(available, this.remaining)
        this.sum += (Number.isFinite(value) ? value : 0) * contribution
        this.weight += contribution
        available -= contribution
        this.remaining -= contribution
        if (this.remaining < 1e-9) {
          this.append(this.sum / this.weight)
          this.sum = 0
          this.weight = 0
          this.remaining = this.ratio
        }
      }
    }
  }

  flush() {
    if (this.closed) return
    this.closed = true
    if (this.weight > 1e-9) this.append(this.sum / this.weight)
    if (this.length > 0) this.emitFrame()
  }

  private append(value: number) {
    const clamped = Math.max(-1, Math.min(1, value))
    this.frame[this.length++] = Math.round(clamped * (clamped < 0 ? 32768 : 32767))
    if (this.length === PCM_FRAME_SAMPLES) this.emitFrame()
  }

  private emitFrame() {
    // DataView makes little endian explicit even on a different browser host.
    // Integer millisecond metadata requires 16-sample boundaries. Preserve every
    // tail sample and add at most 15 zero samples (less than 1 ms) at the very end.
    const paddedLength = Math.ceil(this.length / 16) * 16
    const buffer = new ArrayBuffer(paddedLength * 2)
    const view = new DataView(buffer)
    for (let index = 0; index < this.length; index++) {
      view.setInt16(index * 2, this.frame[index], true)
    }
    this.length = 0
    this.emit(buffer)
  }
}
