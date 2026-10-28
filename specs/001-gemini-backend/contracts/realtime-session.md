# Contract: Shared Session and Gemini Wire Adapter

## App boundary and common events

Retain ConversationHandler lifecycle, receive/emit, voice/personality, say/interrupt,
observers, and refresh_instructions. Shared implementation remains in huggingface_realtime.py.
Two actual provider transports justify common connect, typed event stream, audio/text send,
tool response/image submission, interrupt, and close operations. Keep HF-specific mutable
configuration behind its implementation; do not expose provider objects to tools/UI.

Normalized events represent ready, audio, transcript, interruption, tool calls/cancellation,
turn completion, resumption updates, closure. Use typed dataclasses/tagged unions and wire
validation; no new public Any/cast signatures. One wire message may yield several events.
Unknown optional events may be logged without sensitive payloads; malformed required
setup/audio/tool content fails the session with a logged, normalized error.

## Gemini setup and audio

Use the documented Developer API BidiGenerateContent endpoint over TLS and documented
API-key header authentication; do not log credential-bearing URLs or protocol frames.
Send setup once with models/<configured model>, AUDIO output, systemInstruction from
existing prompt assembly, speech voice, effective function declarations, both transcript
options, automatic activity detection, contextWindowCompression.slidingWindow, and
sessionResumption. Wait for setupComplete before accepting input or tool work.

Send realtimeInput.audio as audio/pcm;rate=<actual input rate>, mono PCM16 little-endian.
Process every serverContent part: inlineData audio, input/output transcription, interrupted,
turnComplete. Honor output MIME rate, normally 24 kHz; reject malformed/unsupported formats.
Resample to the public SDK playback rate before enqueue. Drain converter delay only at a
normal audio-turn end, discard buffered samples on interruption/disconnection.

Gemini automatic VAD detects turn boundaries; local VAD retains movement/ducking roles.
Server interrupted confirms playback flush. App interrupt sends a documented terminating
clientContent turn with turnComplete, flushes SDK/queues, and advances output epoch. Suppress
late output until a valid next-turn boundary. Do not combine automatic VAD with manual
activityStart/activityEnd. Test remote cancellation and late-output suppression together;
queue clearing alone does not satisfy interruption.

## Functions, silent completion, and snapshots

Register effective permitted tool specs only. Preserve valid names or use deterministic
aliases with collision-free reverse mapping. Conservative name subset: letters, digits,
underscore, dash; maximum 128 characters. Validate supported parametersJsonSchema at setup;
unsupported declarations produce a specific corrective error with the app tool ID.

Handle every functionCalls entry. Register logical_session_id/call_id before dispatch via
BackgroundToolManager. Preserve IDs in functionResponses. Use nonblocking calls and SILENT
completion for needs_response=False; do not request gratuitous spoken follow-up.
toolCallCancellation cancels eligible work and suppresses results, not physical effects.
App-local idle tools must not produce fictitious model function results.

For successful camera results, submit sanitized metadata and exactly one image/jpeg realtime
image associated with that active invocation. b64_im never enters text results/transcripts.
No automatic recapture or re-execution on send failure. No image on disabled/failed capture,
no periodic source. Shared permissions apply before any capture or transmission.

## Ownership, recovery, and errors

Events carry connection generation; tool calls carry logical session/call ID; playback
carries response epoch. Invalidate ownership before asynchronous shutdown and check it
before observer callbacks, enqueueing, action dispatch, images, and result submission.

Keep the latest valid resumable handle in memory. Retry may use it only with unchanged
model/voice/profile/toolset/injected-memory revision. Changing any of those or provider
invalidates it. Resumed sessions reconcile known pending calls; duplicate IDs never execute
again. Unknown completion is reported as uncertain. Known completed results may be sent
again only to satisfy that same resumed call, without repeating its action. Fresh sessions
receive no old audio/tool/transcript queues or prior live conversation history.

GoAway warns of approaching closure; actual close waits for explicit Retry. resumable=false,
invalid handle, or rejected resumption makes continuity unavailable; a fresh connection
within the user's retry must be disclosed. No automatic Gemini reconnect or provider fallback.
Tokens and credentials are never durable or logged. Existing HF automatic retry behavior is
preserved; Gemini must not accidentally enter HF retry loops through shared orchestration.
