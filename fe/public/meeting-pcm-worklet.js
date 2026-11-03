/* global AudioWorkletProcessor, registerProcessor */
class MeetingPcmProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.stopped = false
    this.port.onmessage = (event) => {
      if (event.data?.type === 'flush') {
        this.stopped = true
        // This message follows every samples message already sent on this port.
        this.port.postMessage({ type: 'flushed' })
      }
    }
  }

  process(inputs) {
    if (this.stopped) return false
    const channels = inputs[0]
    if (channels?.[0]?.length) {
      const mono = new Float32Array(channels[0].length)
      for (const channel of channels) {
        for (let index = 0; index < mono.length; index++) {
          mono[index] += channel[index] / channels.length
        }
      }
      this.port.postMessage({ type: 'samples', samples: mono }, [mono.buffer])
    }
    return true
  }
}

registerProcessor('meeting-pcm', MeetingPcmProcessor)
