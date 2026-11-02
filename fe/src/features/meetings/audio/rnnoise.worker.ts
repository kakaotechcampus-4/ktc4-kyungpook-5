import { Rnnoise } from '@shiguredo/rnnoise-wasm'
import { RnnoiseStream } from './rnnoiseStream'

const channel = self as unknown as {
  onmessage: ((event: MessageEvent) => void) | null
  postMessage: (message: unknown, transfer?: Transferable[]) => void
}
let stream: RnnoiseStream | undefined
channel.onmessage = (event) => {
  void (async () => {
    try {
      if (event.data.type === 'init') {
        const model = await Rnnoise.load({ assetsPath: event.data.assetsPath })
        if (model.frameSize !== 480) throw new Error('Unsupported RNNoise frame size')
        stream = new RnnoiseStream(model.createDenoiseState(), (samples) => {
          channel.postMessage({ type: 'samples', samples }, [samples.buffer])
        })
        channel.postMessage({ type: 'ready' })
      } else if (event.data.type === 'samples') {
        if (!stream) throw new Error('RNNoise is not ready')
        stream.push(event.data.samples)
        channel.postMessage({ type: 'accepted', samples: event.data.samples.length })
      } else if (event.data.type === 'flush') {
        if (!stream) throw new Error('RNNoise is not ready')
        stream.finish()
        stream = undefined
        channel.postMessage({ type: 'flushed' })
      }
    } catch {
      channel.postMessage({ type: 'error' })
    }
  })()
}
