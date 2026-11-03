import { useState } from 'react'
import { Button } from '@/shared/ui/Button'
import { useMeetingAudio, type AudioPhase, type MeetingAudioOptions } from './useMeetingAudio'

const LABELS: Record<AudioPhase, string> = {
  idle: '마이크를 켜면 확정된 전사가 최신순으로 표시돼요.',
  connecting: '음성 전송을 준비하고 있어요.',
  permission: '브라우저에서 마이크 권한을 허용해 주세요.',
  recording: '마이크가 켜졌어요. 음성을 서버로 보내고 있어요.',
  paused: '일시정지했어요. 이 동안 한 말은 기록되지 않아요.',
  flushing: '마지막 음성을 보내고 있어요.',
  ending: '서버의 마지막 음성 수신을 확인하고 있어요.',
  processing: '마이크를 껐어요. 마지막 전사와 자료 응답을 기다리고 있어요.',
  completed: '마지막 전사와 자료 응답 처리가 완료됐어요.',
  error: '음성 처리가 완료되지 않았어요.',
}

export function MicControls(props: MeetingAudioOptions) {
  return <MeetingMicControls key={props.meetingId} {...props} />
}

function MeetingMicControls(props: MeetingAudioOptions) {
  const audio = useMeetingAudio(props)
  const [rnnoise, setRnnoise] = useState(false)
  const preparing = audio.phase === 'connecting' || audio.phase === 'permission'
  const processing =
    audio.phase === 'flushing' || audio.phase === 'ending' || audio.phase === 'processing'
  const elapsedSeconds = Math.floor(audio.durationMs / 1000)
  return (
    <div className="flex flex-col gap-[10px] rounded-[14px] border border-soft bg-bg p-[16px]">
      <p role="status" className="text-[12px] leading-[19px] text-ink2">
        {LABELS[audio.phase]}
      </p>
      {audio.durationMs > 0 && (
        <p className="text-[11px] text-mute">
          전송 {Math.floor(elapsedSeconds / 60)}:{String(elapsedSeconds % 60).padStart(2, '0')}
        </p>
      )}
      {audio.phase === 'recording' && (
        <div className="flex items-center gap-3">
          <span className="shrink-0 text-[12px] text-ink2">마이크 입력</span>
          <div
            role="meter"
            aria-label="마이크 입력 레벨"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(audio.inputLevel * 100)}
            className="h-2 w-full max-w-[180px] overflow-hidden rounded-full bg-line"
          >
            <div
              className="h-full rounded-full bg-blue-600 transition-[width] duration-100"
              style={{ width: `${audio.inputLevel * 100}%` }}
            />
          </div>
        </div>
      )}
      {audio.phase === 'recording' && audio.noiseSuppression === false && (
        <p className="text-[11px] leading-5 text-mute">
          이 브라우저에서 마이크 잡음 억제가 꺼져 있어요. 조용한 장소에서 사용해 주세요.
        </p>
      )}
      {audio.error && (
        <p role="alert" className="text-[12px] leading-[19px] text-failed">
          {audio.error}
        </p>
      )}
      {(audio.phase === 'idle' || audio.phase === 'error') && (
        <label className="flex items-start gap-2 text-[12px] leading-[19px] text-ink2">
          <input type="checkbox" checked={rnnoise} onChange={(event) => setRnnoise(event.target.checked)} />
          <span>실험적 RNNoise 잡음 억제 사용 (작은 목소리가 누락될 수 있어요)</span>
        </label>
      )}
      <div className="flex flex-wrap gap-[8px]">
        {(audio.phase === 'idle' || audio.phase === 'error') && (
          <Button onClick={() => void audio.start(rnnoise)}>
            {audio.phase === 'error' ? '마이크 다시 시작' : '마이크 켜기'}
          </Button>
        )}
        {audio.phase === 'recording' && (
          <Button variant="secondary" onClick={audio.pause}>
            일시정지
          </Button>
        )}
        {audio.phase === 'paused' && <Button onClick={audio.resume}>다시 녹음</Button>}
        {(audio.phase === 'recording' || audio.phase === 'paused') && (
          <Button onClick={() => void audio.stop()}>마이크 끄고 마지막 전사 확인</Button>
        )}
        {(preparing || processing) && (
          <Button variant="secondary" onClick={audio.abort}>
            {preparing ? '시작 취소' : '대기 중단'}
          </Button>
        )}
      </div>
      <p className="text-[10.5px] leading-[17px] text-mute">
        마이크를 끈 뒤 마지막 전사 확인까지 기다려 주세요. 처리 중 이 화면을 닫으면 마지막 결과를
        확인하지 못할 수 있어요.
      </p>
    </div>
  )
}
