const FRAME = 480

type Denoise = { processFrame: (samples: Float32Array) => number; destroy: () => void }

// RNNoise emits each frame one frame later. Keep its state for the entire capture.
export class RnnoiseStream {
  private frame = new Float32Array(FRAME)
  private pending = 0
  private inputSamples = 0
  private outputSamples = 0
  private primed = false
  constructor(private readonly denoiser: Denoise, private readonly emit: (samples: Float32Array) => void) {}

  push(samples: Float32Array) {
    this.inputSamples += samples.length
    let offset = 0
    while (offset < samples.length) {
      const count = Math.min(FRAME - this.pending, samples.length - offset)
      this.frame.set(samples.subarray(offset, offset + count), this.pending)
      this.pending += count
      offset += count
      if (this.pending === FRAME) this.process()
    }
  }

  finish() {
    if (this.pending) this.process()
    if (this.inputSamples) this.process()
    this.denoiser.destroy()
  }

  private process() {
    for (let i = 0; i < FRAME; i++) this.frame[i] *= 32768
    this.denoiser.processFrame(this.frame)
    if (this.primed) {
      const length = Math.min(FRAME, this.inputSamples - this.outputSamples)
      const out = this.frame.slice(0, length)
      for (let i = 0; i < length; i++) out[i] /= 32768
      if (length) this.emit(out)
      this.outputSamples += length
    }
    this.primed = true
    this.frame.fill(0)
    this.pending = 0
  }
}
