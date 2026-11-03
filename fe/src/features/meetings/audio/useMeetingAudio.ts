import { useCallback, useEffect, useRef, useState } from 'react'
import { prepareRnnoise, startPcmCapture, type PcmCapture, type PreparedRnnoise } from './capture'
import { MeetingAudioTransport, type AudioGap, type AudioProgress } from './transport'

export type AudioPhase =
  | 'idle'
  | 'connecting'
  | 'permission'
  | 'recording'
  | 'flushing'
  | 'ending'
  | 'processing'
  | 'completed'
  | 'error'
interface AudioState extends AudioProgress {
  phase: AudioPhase
  error: string | null
  inputLevel: number
  noiseSuppression?: boolean
}
const INITIAL: AudioState = {
  phase: 'idle',
  error: null,
  inputLevel: 0,
  sentFrames: 0,
  acceptedFrames: 0,
  durationMs: 0,
}

function microphoneError(error: unknown) {
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError') return '마이크 권한을 허용해야 회의를 녹음할 수 있어요.'
    if (error.name === 'NotFoundError') return '연결된 마이크를 찾지 못했어요.'
    if (error.name === 'NotReadableError')
      return '마이크를 사용할 수 없어요. 다른 앱의 마이크 사용을 확인해 주세요.'
  }
  return error instanceof Error ? error.message : '마이크를 시작하지 못했어요.'
}

export interface MeetingAudioOptions {
  meetingId: string
  onCompleted: () => void
  onRefresh: () => void
  onActiveChange?: (active: boolean) => void
  onPhaseChange?: (phase: AudioPhase) => void
  onAudioGap?: (gap: AudioGap) => void
}

export function useMeetingAudio({
  meetingId,
  onCompleted,
  onRefresh,
  onActiveChange,
  onPhaseChange,
  onAudioGap,
}: MeetingAudioOptions) {
  const [state, setState] = useState<AudioState>(INITIAL)
  const capture = useRef<PcmCapture | null>(null)
  const transport = useRef<MeetingAudioTransport | null>(null)
  const generation = useRef(0)
  const busy = useRef(false)
  const stopping = useRef(false)
  const callbacks = useRef({ onCompleted, onRefresh, onActiveChange, onPhaseChange, onAudioGap })
  useEffect(() => {
    callbacks.current = { onCompleted, onRefresh, onActiveChange, onPhaseChange, onAudioGap }
  }, [onCompleted, onRefresh, onActiveChange, onPhaseChange, onAudioGap])

  useEffect(() => {
    callbacks.current.onActiveChange?.(!['idle', 'error', 'completed'].includes(state.phase))
    callbacks.current.onPhaseChange?.(state.phase)
  }, [state.phase])

  const cancel = useCallback(() => {
    generation.current++
    capture.current?.cancel()
    capture.current = null
    transport.current?.dispose()
    transport.current = null
    busy.current = false
    stopping.current = false
  }, [])

  useEffect(
    () => () => {
      cancel()
      callbacks.current.onActiveChange?.(false)
      callbacks.current.onPhaseChange?.('idle')
    },
    [meetingId, cancel],
  )

  const start = useCallback(async (rnnoise = false) => {
    if (busy.current) return
    cancel()
    busy.current = true
    const run = generation.current
    const active = () => generation.current === run
    const fail = (error: unknown) => {
      if (!active()) return
      capture.current?.cancel()
      capture.current = null
      transport.current?.dispose()
      transport.current = null
      busy.current = false
      setState((previous) => ({ ...previous, phase: 'error', error: microphoneError(error), inputLevel: 0 }))
      callbacks.current.onRefresh()
    }
    setState({ ...INITIAL, phase: 'connecting' })
    const connection = new MeetingAudioTransport(meetingId, {
      onProgress: (progress) => {
        if (active()) setState((previous) => ({ ...previous, ...progress }))
      },
      onProcessing: () => {
        if (active()) setState((previous) => ({ ...previous, phase: 'processing' }))
      },
      onTranscript: () => {
        if (active()) callbacks.current.onRefresh()
      },
      onGap: (gap) => {
        if (!active()) return
        callbacks.current.onAudioGap?.(gap)
        setState((previous) => ({
          ...previous,
          error: '알아듣지 못한 음성 구간이 있어요. 다른 음성 전송은 계속하고 있어요.',
        }))
      },
      onWarning: (message) => {
        if (active()) setState((previous) => ({ ...previous, error: message }))
      },
      onFailure: fail,
    })
    transport.current = connection
    let prepared: PreparedRnnoise | undefined
    try {
      if (rnnoise) {
        prepared = await prepareRnnoise()
        if (!active() || !busy.current) { prepared.dispose(); return }
      }
      await connection.connect()
      if (!active() || !busy.current) { prepared?.dispose(); return }
      setState((previous) => ({ ...previous, phase: 'permission' }))
      const microphone = await startPcmCapture(
        (frame) => connection.sendFrame(frame),
        fail,
        (inputLevel) => {
          if (active()) setState((previous) => ({ ...previous, inputLevel }))
        },
        prepared,
      )
      prepared = undefined
      if (!active() || !busy.current) {
        microphone.cancel()
        return
      }
      capture.current = microphone
      setState((previous) => ({ ...previous, phase: 'recording', noiseSuppression: microphone.noiseSuppression }))
    } catch (error) {
      prepared?.dispose()
      fail(error)
    }
  }, [meetingId, cancel])

  const stop = useCallback(async () => {
    if (stopping.current || state.phase !== 'recording' || !capture.current || !transport.current)
      return
    stopping.current = true
    const run = generation.current
    const microphone = capture.current
    const connection = transport.current
    setState((previous) => ({ ...previous, phase: 'flushing', inputLevel: 0 }))
    try {
      await microphone.stop()
      if (generation.current !== run) return
      capture.current = null
      setState((previous) => ({ ...previous, phase: 'ending' }))
      await connection.end()
      if (generation.current !== run) return
      busy.current = false
      setState((previous) => ({ ...previous, phase: 'completed' }))
      callbacks.current.onRefresh()
      // The server finalized the meeting before this successful audio.completed.
      callbacks.current.onCompleted()
    } catch (error) {
      if (generation.current !== run) return
      cancel()
      setState((previous) => ({ ...previous, phase: 'error', error: microphoneError(error), inputLevel: 0 }))
      callbacks.current.onRefresh()
    }
  }, [state.phase, cancel])

  const abort = useCallback(() => {
    cancel()
    setState((previous) => ({
      ...previous,
      phase: 'error',
      inputLevel: 0,
      error: '음성 전송을 중단했어요. 마지막 전사 완료는 확인되지 않았어요.',
    }))
    callbacks.current.onRefresh()
  }, [cancel])

  return { ...state, start, stop, abort }
}
