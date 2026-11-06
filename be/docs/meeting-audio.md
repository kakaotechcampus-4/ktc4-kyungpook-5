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
   `errorCount` mean some work failed: STT/persistence errors or a failed lookup
   judgment (`CONTEXT_PROCESSING_FAILED`). A task-extraction-only failure is not
   counted; it stays in the agent job's per-feature errors and the decision's
   `PARTIAL` status (#249). `audio.error` gives a safe code/message and
   affected segment or time range when known. STT error `startMs`/`endMs` use the
   same meeting timeline as `transcript.final` and `audio.no_transcript`, including
   `streamOffsetMs`; incoming audio metadata remains stream-relative. Read persisted transcripts, jobs,
   decisions and candidates after reconnect. No dummy transcript is substituted.

`audioSeq`, transcript `seq`, and transcript change `cursor` are separate axes.
Speech utterance WAV files are saved in the configured storage backend before STT;
frame-level resume state is held in process memory for at most 60 seconds.
Silence is suppressed by WebRTC VAD and a centered 20ms RMS floor (200ms pre-roll, 600ms
silence endpoint, at least 160ms voiced audio, maximum 15s segments). Noise can
still pass or quiet speech can be missed; this has not been evaluated on beta
devices. The RMS threshold is adjustable
with `AUDIO_VAD_RMS_THRESHOLD` (default 450 on signed PCM16 values). A provider that
returns empty transcript text emits `audio.no_transcript` for the real voiced
interval without creating a transcript row. The FE can show “알아듣지 못함” for
that gap. No placeholder text is saved and AI is not called for that gap. Pure
silence produces no utterance or transcript row. Provider failures persist as
FAILED STT jobs.

The receiver, one ordered STT worker, and AI processing are separate. STT saves
segments in speech order. Each saved segment then starts its own AI task
(judgment + task extraction) without waiting for earlier ones; at most 4 run at
once (`ai_concurrency`) and the rest wait in arrival order without blocking STT
(#240). Within one task, judgment and extraction start together, but `judgment`
is committed and broadcast as soon as the lookup judgment finishes; it does not
wait for extraction (#249). At that moment the job is still `RUNNING`. Extraction
then finishes in the same task, saving candidates and the final job status, and
may change the decision to `PARTIAL`. Candidates are not broadcast; clients read
them again. Results are broadcast as each judgment finishes, so `judgment` messages can
arrive out of speech order; clients match them by `segmentId`. `AUDIO_BACKPRESSURE`
is an explicit failure only if queued speech exceeds the STT worker capacity (8
segments); slow AI no longer causes it. There is no distributed queue or replay of
raw frames. `end` and disconnect both wait for running AI tasks, so their decisions
are still saved. Abrupt disconnect keeps queued utterances and retains the received tail for resume.
Expiry persists that tail and marks the interrupted meeting FAILED.
On an unexpected disconnect, the single server keeps the VAD tail, accepted frame
sequence, timestamps and hashes of at most 256 recent frames for 60 seconds after
the disconnect, without waiting for the previous worker. It does not keep a separate unbounded frame buffer.
The client retains unsafely acknowledged frames locally and reconnects with
`{"type":"resume","format":"pcm_s16le","sampleRate":16000,"channels":1,"lastAckSeq":N}`.
`audio.ready` includes `resumed:true`, `lastAudioSeq`, `endMs`, and the original
`streamOffsetMs`. Send retained frames with their original sequence/time from the
server's next expected sequence. If an ACK was lost, an exact retained frame replay
is acknowledged without reprocessing; a different replay is AUDIO_REPLAY_MISMATCH.
Client audio captured after the server's last accepted sequence must be retransmitted;
the server cannot recover frames absent from both sides. Expired window, server
restart, or lastAckSeq outside the retained range returns AUDIO_RESUME_UNAVAILABLE.
The resume handshake does not wait for old STT or AI work. New STT waits for the
preceding STT worker to preserve transcript order; completion waits for all prior
AI tasks and retains their failures. The last 16 audio errors are repeated on
resume, and the total error count includes every connection.
The original member/meeting authorization and RECORDING status are rechecked. New
capture on a stopped/completed meeting is rejected. A new `start` while a resume
state exists returns AUDIO_RESUME_REQUIRED. Resume is single-process only; no
cross-process or restart durability is claimed. Read stored transcripts by cursor.

Configure `STT_URL` as the full gateway endpoint and `STT_API_KEY` as its bearer key,
plus `STT_MODEL` and `STT_TIMEOUT_SECONDS` (default 60). The adapter posts multipart
`file` (16kHz mono WAV), `model`, and `language`. For MLAPI, use the Whisper
deployment's model-specific base URL followed by `/v1/audio/transcriptions` and
model ID `openai/whisper-large-v3`. The adapter accepts both the gateway's
`{"transcript":{"text":"..."}}` response and top-level `{"text":"..."}`.
Missing configuration returns STT_NOT_CONFIGURED before recording starts.

The old HTTP `audio-chunks` endpoint only runs its legacy stub under TEST_MODE.
Normal mode returns 501 HTTP_AUDIO_NOT_IMPLEMENTED, directing real audio to WS.
HTTP `finish` returns 409 AUDIO_STREAM_ACTIVE during live capture; use WS end so
pending speech cannot be lost by claiming immediate completion.
