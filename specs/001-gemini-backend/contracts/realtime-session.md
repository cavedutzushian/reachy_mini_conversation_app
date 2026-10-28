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

## Interruption state machine

Use one ordered reader per socket. Assign generation/epoch at receipt, before downstream
queueing; consumers must not relabel delayed chunks with their current epoch. Normal output
is ACCEPTING. Evaluate interrupted/control flags before media in the same envelope.

| Current state / event | Required action | Next state |
| --- | --- | --- |
| ACCEPTING + interrupted | Advance epoch; flush SDK/queues/resampler; mark outgoing fragment interrupted; discard assistant media in this envelope | DRAINING_INTERRUPTED_TURN |
| DRAINING + assistant audio/output transcript/old-turn work | Discard, including delayed queued chunks; never turn discarded work into an action | DRAINING_INTERRUPTED_TURN |
| DRAINING + generationComplete | Do not reopen output | DRAINING_INTERRUPTED_TURN |
| DRAINING + turnComplete | Discard any bundled abandoned assistant media, then reopen only for subsequent messages | ACCEPTING with new epoch |
| DRAINING + another interrupted | Flush again and restart the five-second boundary deadline; no concurrent restart | DRAINING_INTERRUPTED_TURN |
| DRAINING + boundary deadline | Invalidate generation/handle and close; announce fresh context; serialize new setup | Disconnected then ACCEPTING only after new setup |
| Any state + explicit app interrupt without a correlated server boundary | Flush/suppress immediately; invalidate socket/handle; announce fresh session and serialize new setup | Disconnected then ACCEPTING after setup |

For normal server-VAD barge-in, interrupted then turnComplete is the provider boundary;
generationComplete is not required for interrupted turns and cannot substitute for it.
Cancellation and resumption control events still update the active ledger/state while output
is draining; only abandoned model output/new action dispatch is suppressed.
Input transcription ordering is independent; preserve user input transcripts without using
them to reopen assistant output. If interrupted and turnComplete coexist, apply both in
that order and discard assistant payload in that envelope. Honor IN_PROGRESS if an
interaction-status field indicates more work; turnComplete is not a global app-idle claim.

Do not send an empty clientContent turnComplete=true as a stop-only acknowledgement: it
requests generation. The explicit-app-interrupt path deliberately starts fresh when no
correlated stop boundary exists, including when generation ended but local playback remains.
Normal barge-in keeps context; its server-marker path calls shared playback flush directly,
not the public app-interrupt reset path. Coalesce repeated app interrupts into one restart, suppress
old callbacks, and never resume the abandoned generation. Gemini automatic VAD remains on;
local VAD still controls ducking/movement, without manual activity markers.

Required fake-wire sequences: split interrupted/turnComplete; both flags together; media
bundled with interrupted; queued old audio consumed after flush; generationComplete without
turnComplete; repeated interrupts; missing boundary; app interrupt after generation ended;
and new assistant output after the valid barrier. Include independent input transcription.

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

LocalStream owns RealtimeSessionState and its lifetime. Define the typed state alongside
shared orchestration and pass it through the handler factory to replacement handlers.
It holds logical ID/configuration revision, resumption eligibility/handle, execution ledger,
and safe continuity status. Handlers own transports/tasks/queues only. Closing a handler
must not erase retained logical state. LocalStream allocates increasing connection generations
across all logical sessions and alone retires state when starting fresh or shutting down.

Check active ownership before every audio send/enqueue, observer call, image submission,
tool dispatch and result delivery. Invalidate the old generation before close/new setup;
a late cleanup task cannot regain media/action ownership. No simultaneous active sockets.
Retain the ledger/handle for same-provider, same-config reconnect even if the handler object
is replaced. Test replacement of the handler itself, not just reopening its socket.

Resume only when the latest state is resumable with a nonempty handle and unchanged
model/voice/profile/toolset/injected-memory revision. A false update clears old eligibility;
do not assume an earlier checkpoint safely restores current context. Missing/rejected resume
visibly starts fresh in the same attempt, within its remaining setup deadline. Keep duplicate
call IDs suppressed across successful resume; known completed results may be resubmitted only
for the same resumed call without re-executing it. Unknown effects are uncertain and never
retried. Fresh sessions inherit no old input/output queues, live history or tool requests.

One LocalStream scheduler handles both providers: retry recoverable failures indefinitely
with backoff 1,2,4,8,16,30,30... seconds. Reset after a completed exchange. Remove nested
handler retries so the cap/deadline policy has one owner. Manual Retry cancels the wait and
schedules one attempt; repeated clicks coalesce. Switching/shutdown cancels waits/attempts
and disposes old logical state. There is no automatic provider switch.

Recoverable: transient network/connection loss, setup/send timeouts, transient rate limiting,
and temporary service errors. Await correction: missing/rejected credentials, invalid
model/voice/schema/request settings, denied access and depleted billing/hard quota. Do not
classify all quota errors alike or expose raw responses. Unknown error classifications wait
for explicit Retry/correction rather than an unchecked automatic storm. GoAway warns of
closure and triggers a serialized same-provider reconnect with retained eligible state.

Use monotonic time: connect plus setupComplete share 15 seconds; each audio/message send
has 5 seconds; graceful close has 5 seconds. Resume rejection and fresh fallback share the
original attempt deadline; a transient failed attempt then enters backoff. Timeout invalidates
ownership before recovery. Bounded cancellation/transport close cannot freeze configuration
or prevent shutdown/switching even if an old cleanup task is slow. Never buffer microphone
audio while disconnected for later transmission.

Provider/setup/prompt changes deliberately invalidate handles and visibly create a new
session, avoiding stale-memory restoration. This is an app consistency policy; it is not
a claim that non-model settings cannot change via provider pause/resume. Handles/credentials
stay in memory, out of logs/status. The 15-minute validation includes automatic reconnects.

## Provider evidence

Event ordering and message semantics: [Live wire reference](https://ai.google.dev/api/live).
Resume/GoAway lifecycle: [session management](https://ai.google.dev/gemini-api/docs/live-api/session-management).
The barrier, state owner, fresh-session fallback and scheduler above are application design
choices derived from those documented events, not measured hardware/provider guarantees.
