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
| gemini_voice | optional nonempty string | Saved > GEMINI_VOICE > Kore; validate Gemini catalog |
| hf_voice | optional nonempty string | New HF-only override; retain legacy startup/profile fallback |
| existing hf_* fields | unchanged | Switching never clears these |

No credentials, handles, transcripts, or tool ledgers are persisted here. Legacy startup
voice remains an HF choice. Provider overrides never rewrite shared profile.md voice fields.
Profile voice is accepted only if valid for the selected provider; show an incompatible
explicit choice with a valid correction. Preserve existing HF fallback behavior.

## Runtime configuration

Effective provider/model/voice and credential-present boolean are safe status fields.
Read GEMINI_API_KEY through existing environment loading. Keys never enter status, settings
writes, errors, or WebSocket debug logs. Use Google's TLS endpoint, not an arbitrary
credential-bearing endpoint selector.

## Session identity and lifecycle

| Field | Type | Ownership/lifetime |
| --- | --- | --- |
| logical_session_id | unique string | Retained only across valid same-config resume |
| connection_generation | increasing integer | Changes on socket/handler replacement |
| response_epoch | increasing integer | Changes on interrupt/flush |
| provider | provider enum | Fixed per logical session |
| state | existing connection-state enum | waiting_for_config, connecting, connected, disconnected, restart_required |
| context_state | new/resumed/unavailable | Distinct from connection state |
| configuration_revision | integer or stable digest | Changes with model/voice/profile/tools/injected memory |
| resumption_handle | optional opaque secret | Memory only, never logged or exposed |
| resumable | boolean | Most recent valid service update governs reuse |

Transitions: waiting_for_config -> connecting after setup; connecting -> connected after
acknowledgement or disconnected on failure; connected -> disconnected on loss. Explicit
Gemini Retry reconnects with a valid same-config handle; rejection visibly creates a new
logical session. Configuration/provider changes invalidate the handle before reconnect.
No input/tool dispatch while disconnected. Reject old generations before audio queue writes,
observer callbacks, image sends, tool dispatch and result handling.

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
