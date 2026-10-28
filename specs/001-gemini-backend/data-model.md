# Data Model: Optional Gemini Conversation Backend

**Spec**: [spec.md](spec.md) | **Session contract**: [realtime-session.md](contracts/realtime-session.md)

## Persisted provider settings

Extend AppSettings additively in settings.json version 1 using the existing atomic merge.
Absent fields preserve legacy HF behavior. Invalid explicit selections fail validation;
invalid saved provider values are logged and normalized to default at startup.

| Field | Type | Validation and precedence |
| --- | --- | --- |
| conversation_backend | optional huggingface/gemini | Saved > environment > huggingface |
| gemini_model | optional nonempty string | Saved > GEMINI_MODEL > gemini-3.8-live; validate supported Live path |
| gemini_voice | optional nonempty string | Saved > compatible personality voice > GEMINI_VOICE > Kore; validate Gemini catalog |
| existing hf_* fields | unchanged | Switching never clears these |

No credentials, handles, transcripts, or tool ledgers are persisted here. Existing HF
startup/profile voice resolution and storage remain unchanged. Gemini override never rewrites
shared profile.md or the saved HF startup voice. With no saved Gemini override, a compatible
personality voice wins over GEMINI_VOICE and Kore; an incompatible personality voice blocks
setup until a valid Gemini override is chosen. A saved override bypasses that incompatibility.
Missing profile voice falls through normally; do not silently skip an incompatible one.

## Runtime configuration

Effective provider/model/voice and credential-present boolean are safe status fields.
Read GEMINI_API_KEY through existing environment loading. Keys never enter status, settings
writes, errors, or WebSocket debug logs. Use Google's TLS endpoint, not an arbitrary
credential-bearing endpoint selector.

## Session-state owner

LocalStream owns one typed RealtimeSessionState, defined alongside shared orchestration in
huggingface_realtime.py. Pass its reference through main.py's existing handler factory into
all replacement handlers for the same logical conversation. It contains identity/configuration,
resume state, invocation ledger, and safe context status; sockets, task queues, and resampler
buffers belong to the replaceable handler. Handler shutdown does not clear the owner's state.
LocalStream alone decides retention or disposal. A LocalStream-wide generation counter stays
monotonic across fresh logical sessions as well as reconnects; new objects cannot reuse old
generation values. An inactive object's late callbacks cannot update the new owner's state.

Retain state for automatic/manual same-provider, same-config recovery. On a valid resume,
the new handler receives the same handle/ledger object. On fresh fallback, provider/config
change, app-interrupt reset or shutdown, invalidate the old object/handle and allocate a new
logical session as applicable. Report any uncertain old actions before discarding old state;
do not transfer their output, queues, or requests to the new conversation.

## Session identity and lifecycle

| Field | Type | Ownership/lifetime |
| --- | --- | --- |
| logical_session_id | unique string | Retained only across valid same-config resume |
| connection_generation | increasing integer | Changes on socket/handler replacement |
| response_epoch | increasing integer | Changes on interrupt/flush |
| provider | provider enum | Fixed per logical session |
| state | existing connection-state enum | waiting_for_config, connecting, connected, disconnected, restart_required; retry wait is disconnected plus retry metadata |
| context_state | new/resumed/unavailable | Distinct from connection state |
| configuration_revision | integer or stable digest | Changes with model/voice/profile/tools/injected memory |
| resumption_handle | optional opaque secret | Memory only, never logged or exposed |
| resumable | boolean | Most recent valid service update governs reuse |

Transitions: waiting_for_config -> connecting after correction; connecting -> connected
after acknowledgement or disconnected on failure; connected -> disconnected on loss.
Recoverable failure schedules an automatic same-provider attempt; permanent authentication/
configuration/access/billing failures wait for correction. Rejected resume clears the handle
and visibly starts a fresh logical session, bounded by the current setup deadline. Provider/
configuration change invalidates state before rebuilding. No input/tool dispatch while not
connected. Reject old generations before audio/observer/image/tool processing.

LocalStream owns one retry counter/timer, independent of handler instances. Delays are
1, 2, 4, 8, 16, 30, 30... seconds without an attempt limit. Reset the counter after a completed
exchange; initial setup alone does not reset a flapping session. Manual Retry cancels a wait
and schedules one immediate attempt. Switching/shutdown cancels timer and in-flight attempt.
Use monotonic deadlines: 15 seconds combined connect/setup, 5 per send, 5 graceful close.
Expose only safe retry_attempt and retry_delay_seconds status, never resume tokens.

The output barrier is ACCEPTING or DRAINING_INTERRUPTED_TURN, tied to current generation and
response epoch. On Gemini interrupted, flush/increment epoch and drain through turnComplete;
only subsequent messages reopen output. generationComplete is not the reopening event.
Process flags before bundled media, suppress the abandoned envelope, and preserve separately
ordered input transcripts. Missing turnComplete for five seconds or an uncorrelated app
interrupt invalidates the socket/handle and visibly starts fresh. Normal barge-in retains
context. The exact sequence tests are in the session contract.

## Invocation ledger

Key: logical_session_id plus provider call_id. Fields: app tool ID, wire alias, origin
generation/epoch, execution state (received/running/completed/cancelled/uncertain), sanitized
result, cancellation eligibility. Register before execution. Duplicate IDs never execute
again. Retain ledger across resume, reconciling callbacks to the current generation only
when their origin belongs to the resumed logical session. Do not automatically retry an
uncertain action. Known completed results may be resubmitted for the same resumed call
without re-execution. End the logical session explicitly rather than evicting IDs in a way
that permits replay. Discard all old-session work on fresh sessions. No durable ledger.

## Transcript and audio entries

Use existing observers and AdditionalOutputs. Transcript runtime entries carry speaker,
text, session/generation, and partial/completed/interrupted state. Add explicit metadata for
interrupted fragments: existing (role,text,final) callbacks alone do not express that state.
Do not mark abandoned partial output completed. No new transcript retention behavior.

Audio carries true sample rate, PCM samples, generation and epoch. Converter state belongs
to an active audio response; drain only on normal completion, discard on interrupt/loss.
Frames sent to LocalStream carry the actual SDK playback sample rate. Do not buffer a
disconnected microphone for later transmission.

## Shared memories and camera images

SavedMemory keeps existing fact IDs/text and persistence. Provider is not part of identity.
Global memory enable controls injection; remember/forget tool access controls mutations.
Disabling memory preserves stored facts. Explicit refresh starts a fresh Gemini session
and clears stale handles. No promise that disabling/deleting a local fact erases provider
knowledge already sent in an active conversation.

One camera image belongs to one permitted invocation. Existing b64_im holds JPEG bytes;
send once as image/jpeg, never in transcript/log text or generic tool output. On failure,
send ordinary error and no image. There is no periodic frame producer or continuous queue.
