import { getAccessToken, getApiBaseUrl } from '@/shared/api/client'
import { PcmFrameClock, PCM_SAMPLE_RATE } from './pcm'

export interface AudioProgress {
  sentFrames: number
  acceptedFrames: number
  durationMs: number
}

export interface AudioGap {
  startMs: number
  endMs: number
}

interface TransportCallbacks {
  onProgress: (progress: AudioProgress) => void
  onProcessing: () => void
  onTranscript: () => void
  onGap: (gap: AudioGap) => void
  onWarning: (message: string) => void
  onFailure: (error: Error) => void
}

export class MeetingAudioTransport {
  private socket: WebSocket | null = null
  private ready = false
  private ending = false
  private completed = false
  private disposed = false
  private failed = false
  private sentFrames = 0
  private acceptedFrames = 0
  private readonly clock = new PcmFrameClock()
  private readyTimer: ReturnType<typeof setTimeout> | undefined
  private endTimer: ReturnType<typeof setTimeout> | undefined
  private resultTimer: ReturnType<typeof setTimeout> | undefined
  private resolveReady: (() => void) | null = null
  private rejectReady: ((error: Error) => void) | null = null
  private resolveEnd: (() => void) | null = null
  private rejectEnd: ((error: Error) => void) | null = null

  constructor(
    private meetingId: string,
    private callbacks: TransportCallbacks,
  ) {}

  connect(): Promise<void> {
    const token = getAccessToken()
    if (!token) return Promise.reject(new Error('로그인한 뒤 마이크를 시작해 주세요.'))
    const url = new URL(
      `${getApiBaseUrl()}/api/v1/meetings/${encodeURIComponent(this.meetingId)}/stream`,
      window.location.href,
    )
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.searchParams.set('token', token)

    return new Promise<void>((resolve, reject) => {
      this.resolveReady = resolve
      this.rejectReady = reject
      this.socket = new WebSocket(url)
      this.socket.binaryType = 'arraybuffer'
      this.readyTimer = setTimeout(() => {
        this.fail(new Error('서버가 음성 수신 준비를 확인하지 않았어요. 마이크는 켜지지 않았어요.'))
      }, 10_000)
      this.socket.onopen = () => {
        if (this.disposed || this.failed) return
        try {
          this.socket?.send(
            JSON.stringify({
              type: 'start',
              format: 'pcm_s16le',
              sampleRate: PCM_SAMPLE_RATE,
              channels: 1,
            }),
          )
        } catch {
          this.fail(new Error('서버에 음성 시작 요청을 보내지 못했어요.'))
        }
      }
      this.socket.onmessage = (event) => this.receive(event.data)
      this.socket.onerror = () =>
        this.fail(new Error('음성 서버에 연결하지 못했어요. 연결 상태를 확인해 주세요.'))
      this.socket.onclose = () => {
        if (!this.disposed && !this.completed && !this.failed) {
          this.fail(new Error('음성 연결이 끊겼어요. 마지막 전사 완료는 확인되지 않았어요.'))
        }
      }
    })
  }

  sendFrame(frame: ArrayBuffer) {
    if (
      !this.ready ||
      this.ending ||
      this.failed ||
      this.disposed ||
      this.socket?.readyState !== WebSocket.OPEN
    ) {
      throw new Error('서버가 음성을 받을 수 없는 상태예요. 전송을 멈췄어요.')
    }
    // Never silently drop frames or let a slow connection grow without a bound.
    if (this.socket.bufferedAmount > 256_000 || this.sentFrames - this.acceptedFrames >= 100) {
      throw new Error('음성 전송이 밀려 마이크를 멈췄어요. 서버가 받은 전사 결과를 확인해 주세요.')
    }
    const metadata = this.clock.next(frame.byteLength)
    this.sentFrames = metadata.audioSeq
    this.socket.send(JSON.stringify(metadata))
    this.socket.send(frame)
    this.publishProgress()
  }

  end(): Promise<void> {
    if (!this.ready || this.failed || this.disposed || this.socket?.readyState !== WebSocket.OPEN) {
      return Promise.reject(
        new Error('마지막 음성을 서버에 전달하지 못했어요. 전사 결과를 확인해 주세요.'),
      )
    }
    this.ending = true
    return new Promise<void>((resolve, reject) => {
      this.resolveEnd = resolve
      this.rejectEnd = reject
      this.endTimer = setTimeout(
        () =>
          this.fail(
            new Error(
              '서버가 마지막 음성 수신을 확인하지 않았어요. 회의는 완료 처리되지 않았어요.',
            ),
          ),
        15_000,
      )
      this.resultTimer = setTimeout(
        () =>
          this.fail(
            new Error(
              '마지막 전사 처리 시간이 길어지고 있어요. 회의는 완료 처리되지 않았어요. 타임라인에서 결과를 확인해 주세요.',
            ),
          ),
        120_000,
      )
      this.socket?.send(JSON.stringify({ type: 'end', lastAudioSeq: this.sentFrames }))
    })
  }

  dispose() {
    if (this.disposed) return
    this.disposed = true
    this.clearTimers()
    const cancelled = new Error('음성 연결을 중단했어요.')
    this.rejectReady?.(cancelled)
    this.rejectEnd?.(cancelled)
    this.socket?.close(1000)
  }

  private receive(raw: unknown) {
    if (typeof raw !== 'string' || this.failed || this.disposed) return
    let event: Record<string, unknown>
    try {
      event = JSON.parse(raw)
    } catch {
      this.fail(new Error('서버 음성 응답을 읽지 못했어요. 전사 결과를 확인해 주세요.'))
      return
    }
    if (!event || typeof event !== 'object') return
    switch (event.type) {
      case 'audio.ready':
        if (this.ready) return
        if (
          (event.sampleRate !== undefined && event.sampleRate !== PCM_SAMPLE_RATE) ||
          (event.channels !== undefined && event.channels !== 1) ||
          (event.format !== undefined && event.format !== 'pcm_s16le')
        ) {
          this.fail(new Error('서버와 마이크의 음성 형식이 맞지 않아요. 마이크는 켜지지 않았어요.'))
          return
        }
        this.ready = true
        clearTimeout(this.readyTimer)
        this.resolveReady?.()
        break
      case 'audio.accepted':
        if (
          typeof event.audioSeq === 'number' &&
          Number.isInteger(event.audioSeq) &&
          event.audioSeq > this.acceptedFrames &&
          event.audioSeq <= this.sentFrames
        ) {
          this.acceptedFrames = event.audioSeq
          this.publishProgress()
        }
        break
      case 'transcript.final':
        this.callbacks.onTranscript()
        break
      case 'audio.no_transcript':
        this.publishGap(event)
        break
      case 'audio.end_ack':
        if (this.ending) {
          clearTimeout(this.endTimer)
          this.callbacks.onProcessing()
        }
        break
      case 'audio.completed':
        if (!this.ending) return
        if (
          event.status !== 'COMPLETED' ||
          (typeof event.errorCount === 'number' && event.errorCount > 0)
        ) {
          this.fail(
            new Error(
              '일부 음성 구간이나 자료 응답 처리에 실패했어요. 저장된 전사와 결과를 확인해 주세요.',
            ),
          )
          return
        }
        this.completed = true
        this.clearTimers()
        this.resolveEnd?.()
        this.socket?.close(1000)
        break
      case 'audio.error':
        if (
          this.ready &&
          (typeof event.startMs === 'number' ||
            event.code === 'CONTEXT_PROCESSING_FAILED' ||
            event.code === 'AUDIO_PROCESSING_FAILED')
        ) {
          this.publishGap(event)
          this.callbacks.onWarning(
            event.code === 'CONTEXT_PROCESSING_FAILED'
              ? '전사는 저장했지만 일부 자료 응답 처리에 실패했어요. 음성 전송은 계속하고 있어요.'
              : '일부 음성을 알아듣거나 저장하지 못했어요. 음성 전송은 계속하고 있어요.',
          )
          this.callbacks.onTranscript()
          return
        }
        this.fail(
          new Error('서버가 음성을 처리하지 못했어요. 전사 결과를 확인한 뒤 다시 시도해 주세요.'),
        )
        break
    }
  }

  private publishGap(event: Record<string, unknown>) {
    if (
      typeof event.startMs === 'number' &&
      typeof event.endMs === 'number' &&
      event.startMs >= 0 &&
      event.endMs >= event.startMs
    ) {
      this.callbacks.onGap({ startMs: event.startMs, endMs: event.endMs })
    }
  }

  private publishProgress() {
    this.callbacks.onProgress({
      sentFrames: this.sentFrames,
      acceptedFrames: this.acceptedFrames,
      durationMs: this.clock.durationMs,
    })
  }

  private fail(error: Error) {
    if (this.failed || this.disposed || this.completed) return
    this.failed = true
    this.clearTimers()
    this.rejectReady?.(error)
    this.rejectEnd?.(error)
    // Browser clients permit 1000 or an application code in 3000–4999.
    this.socket?.close(4000)
    this.callbacks.onFailure(error)
  }

  private clearTimers() {
    clearTimeout(this.readyTimer)
    clearTimeout(this.endTimer)
    clearTimeout(this.resultTimer)
  }
}
