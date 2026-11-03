import { PcmFramer } from './pcm'
import RnnoiseWorker from './rnnoise.worker?worker'

export interface PcmCapture {
  noiseSuppression?: boolean
  stop: () => Promise<void>
  cancel: () => void
  // A disabled track keeps producing silent samples, so frames and their timeline continue.
  setPaused: (paused: boolean) => void
}

export interface PreparedRnnoise {
  context: AudioContext
  denoiser: Worker
  dispose: () => void
}

export async function prepareRnnoise(): Promise<PreparedRnnoise> {
  if (!window.AudioContext || !window.AudioWorkletNode || !window.Worker)
    throw new Error('이 브라우저는 RNNoise 잡음 억제를 지원하지 않아요.')
  const context = new AudioContext({ latencyHint: 'interactive', sampleRate: 48000 })
  let denoiser: Worker | undefined
  const dispose = () => {
    denoiser?.terminate()
    if (context.state !== 'closed') void context.close().catch(() => undefined)
  }
  try {
    if (context.sampleRate !== 48000) throw new Error('이 기기에서는 RNNoise의 48kHz 입력을 사용할 수 없어요.')
    denoiser = new RnnoiseWorker()
    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('잡음 제거 준비 시간이 초과됐어요.')), 5000)
      denoiser!.onmessage = (event: MessageEvent) => {
        if (event.data?.type === 'ready') { clearTimeout(timer); resolve() }
        if (event.data?.type === 'error') { clearTimeout(timer); reject(new Error('잡음 제거를 시작하지 못했어요.')) }
      }
      denoiser!.onerror = () => { clearTimeout(timer); reject(new Error('잡음 제거를 시작하지 못했어요.')) }
      denoiser!.postMessage({ type: 'init', assetsPath: new URL(`${import.meta.env.BASE_URL}rnnoise`, location.href).href })
    })
    return { context, denoiser, dispose }
  } catch (error) {
    dispose()
    throw error
  }
}

export async function startPcmCapture(
  onFrame: (frame: ArrayBuffer) => void,
  onFailure: (error: Error) => void,
  onLevel: (level: number) => void,
  prepared?: PreparedRnnoise,
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
  let denoiser: Worker | null = null
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
    denoiser?.terminate()
    if (context && context.state !== 'closed') void context.close().catch(() => undefined)
  }

  try {
    context = prepared?.context ?? new AudioContext({ latencyHint: 'interactive' })
    denoiser = prepared?.denoiser ?? null
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
    let pendingNoiseSamples = 0
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
          if (denoiser) {
            pendingNoiseSamples += samples.length
            if (pendingNoiseSamples > 96000) throw new Error('잡음 처리가 지연되어 음성 전송을 멈췄어요.')
            denoiser.postMessage({ type: 'samples', samples }, [samples.buffer])
          } else {
            framer.push(samples)
          }
        } else if (event.data?.type === 'flushed') {
          if (denoiser) denoiser.postMessage({ type: 'flush' })
          else { framer.flush(); resolveFlush?.() }
        }
      } catch (error) {
        const failure = error instanceof Error ? error : new Error('음성 전송에 실패했어요.')
        rejectFlush?.(failure)
        cleanup()
        onFailure(failure)
      }
    }
    if (denoiser) denoiser.onmessage = (event: MessageEvent) => {
      if (closed) return
      if (event.data?.type === 'accepted') {
        pendingNoiseSamples = Math.max(0, pendingNoiseSamples - event.data.samples)
      } else if (event.data?.type === 'samples' && event.data.samples instanceof Float32Array) {
        try { framer.push(event.data.samples) } catch {
          const error = new Error('음성 전송 중 오류가 발생했어요. 저장된 전사를 확인해 주세요.')
          rejectFlush?.(error)
          cleanup()
          onFailure(error)
        }
      } else if (event.data?.type === 'flushed') {
        try { framer.flush(); resolveFlush?.() } catch {
          const error = new Error('마지막 음성 전송에 실패했어요. 저장된 전사를 확인해 주세요.')
          rejectFlush?.(error)
          cleanup()
          onFailure(error)
        }
      } else if (event.data?.type === 'error') {
        const error = new Error('잡음 제거 중 오류가 발생했어요. 저장된 전사를 확인해 주세요.')
        rejectFlush?.(error)
        cleanup()
        onFailure(error)
      }
    }
    if (denoiser) denoiser.onerror = () => {
      const error = new Error('잡음 제거 중 오류가 발생했어요. 저장된 전사를 확인해 주세요.')
      rejectFlush?.(error)
      cleanup()
      onFailure(error)
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
    if (stream.getAudioTracks().some((track) => track.readyState === 'ended'))
      throw new Error('마이크 연결이 끊겼어요. 다시 시도해 주세요.')
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
      setPaused: (paused) => {
        stream.getAudioTracks().forEach((track) => {
          track.enabled = !paused
        })
      },
    }
  } catch (error) {
    cleanup()
    throw error
  }
}
