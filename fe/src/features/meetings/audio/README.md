# 회의 연속 음성 adapter

`MicControls`는 `meetingId`, `onCompleted`, `onRefresh`를 받는다. `onActiveChange`는 음성 연결 준비부터 최종 처리까지 true이므로 부모의 별도 HTTP 종료 버튼을 잠그는 데 사용한다. `onAudioGap({startMs,endMs})`는 인식하지 못한 구간을 타임라인에 남기는 콜백이다.

1. 사용자 클릭 후 WS `/api/v1/meetings/{id}/stream?token=opaque` 연결.
2. `start {format:'pcm_s16le',sampleRate:16000,channels:1}` 전송.
3. `audio.ready`를 받아 형식을 확인한 후에만 마이크 권한과 AudioWorklet 캡처 시작. 준비 시간 초과에는 마이크를 요청하지 않는다.
4. AudioWorklet의 연속 mono 샘플을 브라우저 실제 sampleRate에서 16k로 변환한다. FE에서 VAD를 수행하지 않는다. 100ms마다 `audio {audioSeq,startMs,endMs}`와 다음 binary PCM16LE를 순서대로 전송한다.
5. 마이크 종료 시 worklet의 모든 선행 샘플을 받은 뒤 resampler와 마지막 PCM tail을 flush한다. BE의 정수 ms/바이트 길이 계약을 위해 최종 tail에만 최대 15개 무음 샘플(1ms 미만)을 덧붙인다. 원본 tail을 버리지 않는다.
6. 마지막 binary 다음 `end {lastAudioSeq}`를 전송한다. `audio.end_ack`의 FINALIZING과 마지막 프레임 번호를 확인한다. 수신 확인은 최종 성공이 아니다.
7. `audio.end_ack` 이후 `audio.completed`의 마지막 프레임 번호, `status === 'COMPLETED'`와 오류 개수를 확인한 뒤에만 `onCompleted`를 호출한다. 이 시점에 서버가 회의 상태까지 finalize했으므로 부모는 재조회한다. `FAILED`와 양수 `errorCount`는 오류로 남긴다.

음성 프레임 seq는 1부터 시작하며 전사 발화 seq/조회 cursor와 공유하지 않는다. 시각은 누적 PCM sample 수로 산정한다. 연결이 끊기거나 전송이 밀리면 프레임을 조용히 버리지 않고 중단 결과를 표시한다. 현재 한계는 WS 재접속/음성 재전송을 제공하지 않는 것이다.

구간 STT 오류와 자료 처리 오류는 경고를 남기고 나머지 음성 입력을 계속한다. 잘못된 프레임/연결 오류는 중단한다. 빈 STT의 `audio.no_transcript`는 gap callback을 호출한다. 마지막 성공은 오직 서버 완료 이벤트로 판단한다.

시간 제한: 서버 준비 10초, 마지막 입력 확인 15초, 최종 처리 120초. 실패한 상태에서는 완료를 주장하지 않고 저장된 전사 재조회를 요청한다. 브라우저 마이크 권한 거절, 지원하지 않는 환경, 연결 종료와 backpressure를 각각 표시한다.

검사:

```sh
node --experimental-transform-types --test src/features/meetings/audio/pcm.test.mjs
npm exec -- eslint src/features/meetings/audio public/meeting-pcm-worklet.js
npm exec -- tsc -b --pretty false
```

변환기 테스트는 48k/44.1k 변환, chunk 경계, PCM endian/clipping, 무음과 tail, audio seq/시각을 검증한다. 실제 기기의 마이크와 인증 BE를 연결한 WS 왕복 확인은 이 수학적 검사와 별개다. AudioWorklet 처리 블록 크기는 고정값으로 가정하지 않는다. 브라우저 API 기준은 [MDN AudioWorkletProcessor.process](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletProcessor/process)를 참고했다.

실패 구간의 `audio.error`와 `audio.no_transcript`는 모두 회의 기준 시각이다. BE의 이 시각 통일 수정과 함께 사용한다. 전사 segment·cursor와 오디오 프레임 번호는 별개다. 기존 음성 기록이 있어 재개할 수 없다는 서버 응답은 저장된 전사 확인과 새 회의 시작을 안내한다.
