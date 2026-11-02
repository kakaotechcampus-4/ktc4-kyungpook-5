import { PcmFramer } from './pcm'

export interface PcmCapture {
  noiseSuppression?: boolean
  stop: () => Promise<void>
  cancel: () => void
}

export async function startPcmCapture(
  onFrame: (frame: ArrayBuffer) => void,
  onFailure: (error: Error) => void,
  onLevel: (level: number) => void,
): Promise<PcmCapture> {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('마이크는 HTTPS 또는 localhost에서 사용할 수 있어요.')
  }
  if (!window.AudioContext || !window.AudioWorkletNode) {
    throw new Error(
      '이 브라우저는 연속 음성 전송을 지원하지 않아요. 최신 Chrome에서 시도해 주세요.',
    )
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    video: false,
  })
  let context: AudioContext | null = null
  let source: MediaStreamAudioSourceNode | null = null
  let worklet: AudioWorkletNode | null = null
  let silentOutput: GainNode | null = null
  let closed = false
  let stopPromise: Promise<void> | null = null
  let rejectFlush: ((error: Error) => void) | null = null
  let flushTimer: ReturnType<typeof setTimeout> | undefined

  function cleanup() {
    if (closed) return
    closed = true
    clearTimeout(flushTimer)
    stream.getTracks().forEach((track) => {
      track.onended = null
      track.stop()
    })
    source?.disconnect()
    worklet?.disconnect()
    worklet?.port.close()
    silentOutput?.disconnect()
    if (context && context.state !== 'closed') void context.close().catch(() => undefined)
  }

  try {
    context = new AudioContext({ latencyHint: 'interactive' })
    await context.audioWorklet.addModule(`${import.meta.env.BASE_URL}meeting-pcm-worklet.js`)
    const framer = new PcmFramer(context.sampleRate, onFrame)
    source = context.createMediaStreamSource(stream)
    worklet = new AudioWorkletNode(context, 'meeting-pcm', {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
    })
    silentOutput = context.createGain()
    silentOutput.gain.value = 0
    let resolveFlush: (() => void) | null = null
    let levelSum = 0
    let levelSamples = 0
    let lastLevelAt = performance.now()
    let displayedLevel = 0
    worklet.port.onmessage = (event: MessageEvent) => {
      if (closed) return
      try {
        if (event.data?.type === 'samples' && event.data.samples instanceof Float32Array) {
          const samples = event.data.samples
          for (const sample of samples) {
            if (Number.isFinite(sample)) levelSum += sample * sample
          }
          levelSamples += samples.length
          const now = performance.now()
          if (now - lastLevelAt >= 100 && levelSamples) {
            // Smooth only the meter; the PCM below remains unchanged.
            const targetLevel = Math.min(1, Math.sqrt(levelSum / levelSamples) * 8)
            displayedLevel += (targetLevel - displayedLevel) * (targetLevel > displayedLevel ? 0.4 : 0.2)
            onLevel(displayedLevel)
            levelSum = 0
            levelSamples = 0
            lastLevelAt = now
          }
          framer.push(samples)
        } else if (event.data?.type === 'flushed') {
          // Flush the resampler and the short final PCM frame before end is sent.
          framer.flush()
          resolveFlush?.()
        }
      } catch (error) {
        const failure = error instanceof Error ? error : new Error('음성 전송에 실패했어요.')
        rejectFlush?.(failure)
        cleanup()
        onFailure(failure)
      }
    }
    worklet.onprocessorerror = () => {
      const error = new Error('마이크 오디오 처리에 실패했어요. 음성 전송을 멈췄어요.')
      rejectFlush?.(error)
      cleanup()
      onFailure(error)
    }
    stream.getAudioTracks().forEach((track) => {
      track.onended = () => {
        if (!closed && !stopPromise) {
          cleanup()
          onFailure(new Error('마이크 연결이 끊겼어요. 전송한 내용은 타임라인에서 확인해 주세요.'))
        }
      }
    })
    source.connect(worklet)
    worklet.connect(silentOutput)
    silentOutput.connect(context.destination)
    await context.resume()
    if (context.state !== 'running')
      throw new Error('마이크 오디오를 시작하지 못했어요. 다시 시도해 주세요.')

    const trackSettings = stream.getAudioTracks()[0]?.getSettings?.()
    return {
      noiseSuppression: trackSettings?.noiseSuppression,
      stop: () => {
        if (stopPromise) return stopPromise
        if (closed) return Promise.reject(new Error('마이크 연결이 이미 종료됐어요.'))
        stopPromise = new Promise<void>((resolve, reject) => {
          resolveFlush = resolve
          rejectFlush = reject
          flushTimer = setTimeout(
            () => reject(new Error('마지막 음성을 확인하지 못했어요. 전사 결과를 확인해 주세요.')),
            3000,
          )
          worklet?.port.postMessage({ type: 'flush' })
        }).finally(cleanup)
        return stopPromise
      },
      cancel: () => {
        rejectFlush?.(new Error('음성 전송을 중단했어요.'))
        cleanup()
      },
    }
  } catch (error) {
    cleanup()
    throw error
  }
}
