# Meeting audio WS contract

`/api/v1/meetings/{meetingId}/stream?token={opaqueSessionToken}` authenticates an
active organization member. Connections can receive existing judgment broadcasts
without starting a recorder. Only one recorder can start for a meeting on this
single-process beta server. Recording consent must already be confirmed on meeting
creation. Query tokens must be redacted from access logs by the deployment.

1. Send JSON `{"type":"start","format":"pcm_s16le","sampleRate":16000,"channels":1}`.
2. Wait for `{"type":"audio.ready","format":"pcm_s16le","sampleRate":16000,"channels":1,"maxFrameMs":1000,"streamOffsetMs":1234}`.
   The offset aligns stream 0ms with `meeting.startedAt`. It is measured from server
   receipt of `start`, before its DB lookup, because the agreed start frame contains
   no client capture timestamp. Network/start-handshake latency is included; it is
   not a measurement of the exact microphone capture wall clock.
3. Send JSON `{"type":"audio","audioSeq":1,"startMs":0,"endMs":100}`,
   immediately followed by one binary PCM16 little-endian frame of 3200 bytes.
   Frames must be contiguous, 1–1000ms each. `audioSeq` starts at 1 and increments
   by one. Timestamps are elapsed capture milliseconds, starting at zero, not wall
   clock timestamps. Every frame is acknowledged with `audio.accepted` + audioSeq.
   Persisted audio chunks and transcript startMs/endMs add streamOffsetMs and use
   the meeting timeline; the incoming metadata continues to start at stream 0ms.
4. Send all remaining captured audio, then JSON `{"type":"end","lastAudioSeq":N}`.
   `audio.end_ack` + `status:FINALIZING` means the tail was queued. Continue waiting.
5. The server flushes the final speech even without trailing silence. Each saved
   final transcript is broadcast as `transcript.final`, with the fields from
   GET transcripts (`id`, `sourceId`, `sourceVersion`, `seq`, `text`, `final`,
   `version`, `startMs`, `endMs`, `decisionJobId`, timestamps) plus `meetingId` and
   `cursor`. `decisionJobId` is initially null because AI runs after STT commits.
   Existing `stage`/`judgment` events associate the later result with segmentId.
6. `audio.completed` + `status:COMPLETED` means all accepted speech STT, persistence,
   and AI tasks finished; the meeting is now COMPLETED. `status:FAILED` and
   `errorCount` mean some work failed. `audio.error` gives a safe code/message and
   affected segment or time range when known. STT error `startMs`/`endMs` use the
   same meeting timeline as `transcript.final` and `audio.no_transcript`, including
   `streamOffsetMs`; incoming audio metadata remains stream-relative. Read persisted transcripts, jobs,
   decisions and candidates after reconnect. No dummy transcript is substituted.

`audioSeq`, transcript `seq`, and transcript change `cursor` are separate axes.
WS WAV/PCM is used in memory for STT and is not written to retained files. Audio
chunk rows keep hash, size, interval and job metadata with null storage_key; final
transcripts remain in the DB. Audio replay/retention is outside this beta slice.
Silence is suppressed by a deterministic 20ms RMS VAD (200ms pre-roll, 600ms silence
endpoint, at least 160ms voiced audio, maximum 15s segments). Loud noise may pass;
this detector has not been evaluated on beta devices. The threshold is adjustable
with `AUDIO_VAD_RMS_THRESHOLD` (default 450 on signed PCM16 values). A provider that
returns empty transcript text persists a final segment with `text:""` and the real
voiced interval, then emits `transcript.final` plus `audio.no_transcript` with its
segmentId. GET transcripts restores this unrecognized interval; the FE can show
“알아듣지 못함” for empty text. No placeholder text is saved and AI is not called for
that gap. Pure silence produces no utterance or transcript row. Provider failures
persist as FAILED STT jobs.

The receiver and bounded ordered STT/AI workers are separate. `AUDIO_BACKPRESSURE`
is an explicit failure if queued speech exceeds the local worker capacity. There
is no distributed queue or replay of raw frames. Abrupt disconnect keeps queued
utterances and flushes received tail, but does not claim a complete meeting.
Reconnecting capture has no resume/replay contract yet: a new start after persisted
speech is rejected with AUDIO_RESUME_UNSUPPORTED. End one live capture with `end`
and create a new meeting for a new capture. GET restores
persisted results, not an unacknowledged network frame.

Configure `STT_URL` as the full gateway endpoint and `STT_API_KEY` as its bearer key,
plus `STT_MODEL` (default whisper-large-v3) and `STT_TIMEOUT_SECONDS` (default 60).
The adapter posts multipart `file` (16kHz mono WAV), `model`, and `language`. It
expects the project's documented gateway response `{"transcript":{"text":"..."}}`.
The actual endpoint request has to be checked against the gateway when credentials
are provided; committed source includes the response contract but no probe script.
Missing configuration returns STT_NOT_CONFIGURED before recording starts.

The old HTTP `audio-chunks` endpoint only runs its legacy stub under TEST_MODE.
Normal mode returns 501 HTTP_AUDIO_NOT_IMPLEMENTED, directing real audio to WS.
HTTP `finish` returns 409 AUDIO_STREAM_ACTIVE during live capture; use WS end so
pending speech cannot be lost by claiming immediate completion.
