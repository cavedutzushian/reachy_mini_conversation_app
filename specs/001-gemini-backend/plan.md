# Implementation Plan: Optional Gemini Conversation Backend

**Branch**: `feat/add-gemini-backend` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-gemini-backend/spec.md`

## Summary

Add Gemini Developer API as an explicit optional provider, retaining Hugging Face as default.
Support voice, interruption, transcripts, essential tools, on-demand snapshots, and shared
memory. Keep shared orchestration in `huggingface_realtime.py`; isolate Gemini wire messages
in `gemini_realtime.py`. Extend existing settings, handler factory, RPC, and restart UI.

## Technical Context

**Language/Version**: Python 3.12 minimum, per the user's clarification and constitution
2.0.0. Implementation must set requires-python to >=3.12, regenerate uv.lock, align older
Python minimums in repository guidance and root README, and validate installation/tests
on Python 3.12 across supported platforms. Strict mypy already targets 3.12. Keep remaining
style rules, including no PEP 695 or future-annotations additions, unless separately amended.
Planning does not change application metadata or guidance files.

**Primary Dependencies**: Existing SDK, NumPy, Pydantic, FastAPI, HF OpenAI client, and locked
websockets 15.0.1. Plan to declare websockets directly and add `soxr>=1.1,<2` for stateful
playback resampling. Both changes were flagged during planning; none were added. No Google
SDK is required. Implementation must resolve supported-platform wheels and regenerate uv.lock.

**Storage**: Existing instance-local settings.json, startup_settings.json, profiles, and
memory store. Add optional non-secret settings; credentials remain in the existing private
environment configuration. Resumption handles and execution ledgers stay in memory only.

**Testing**: pytest/asyncio with fake wire sessions, RPC/settings tests, HF regression tests,
streaming audio tests, and robot acceptance. Ordinary automated tests require no paid access.

**Target Platform**: Linux, macOS, Windows and supported Reachy deployments; public SDK APIs only.

**Project Type**: Python robot application with local audio and JSON-RPC settings UI.

**Performance Goals**: Spec SC-002 through SC-011: 15 minutes/10 exchanges, interruption within
one second in 9/10 trials, ten clean switches, and no replayed actions. Evidence is recorded
in quickstart.md. On 2026-10-30, the user waived interruption timing and accepted that item
as complete for personal customization; no measured timing pass is claimed. The remaining
goals, including 15-minute/10-exchange endurance, are unchanged.

**Personal closeout (2026-10-30)**: the final real-robot trial completed fifteen minutes
and fourteen spoken exchanges. The user accepted the recorded live/offline evidence for
T046 closure with untested service-limit/prolonged-real-network-outage scenarios retained
as limitations. Interruption timing remains waived, not experimentally passed. See the
final quickstart.md closeout for SDK communication errors and other validation limits.

**Constraints**: One active provider, automatic recovery for both providers with 30-second
maximum backoff, 15-second setup / 5-second send / 5-second close deadlines, fresh Gemini
sessions for app-chosen configuration changes,
provider-specific voices, 24 kHz Gemini output, no continuous video, shared memory under
existing controls, and no live-history transfer between providers or credential exposure.

**Scale/Scope**: One robot, two providers, one active conversation. This command ends at design.

## Constitution Check

*GATE: Evaluated before research and rechecked after design.*

| Gate | Before research | After design |
| --- | --- | --- |
| Python 3.12 minimum | Pass: constitution 2.0.0 selects the baseline | Pass by design: metadata/guidance/lock alignment and 3.12 validation required |
| SDK public API only | Pass: existing media/tool APIs | Pass: public audio/sample-rate APIs |
| Shared behavior in realtime module | Pass: no second app loop | Pass: shared handler in huggingface_realtime.py |
| Focused minimal change | Pass: one optional backend | Pass: two transports, no registry/new database |
| Typed boundaries and graceful errors | Pass: required by spec | Pass: validated wire events, errors, ownership |
| Essential tests | Pass: behavior scenarios defined | Pass: HF regression, protocol, lifecycle, robot matrix |
| Dependency changes flagged | Pass: none added | Pass: websockets ownership and soxr flagged |
| Documentation and diagram | Pass: protected files unchanged | Pass: root README/env updates and diagram flag planned |

The user explicitly authorized personal-only customization: local implementation and
simulated tests may proceed without an upstream Issue or maintainer agreement. This scoped
instruction supersedes the contribution gate for this local work only. No PR or publication
is authorized. Paid API calls, service/account eligibility, usage/data budget, physical robot
trials, and platform checks unavailable here remain deferred and must not be reported passed.
A green local gate is still required; the ratification-date TODO remains separate governance.

## Project Structure

### Documentation (this feature)

```text
specs/001-gemini-backend/
  spec.md
  plan.md
  research.md
  data-model.md
  quickstart.md
  contracts/
    backend-selection.md
    realtime-session.md
```

tasks.md tracks implementation against this plan and the clarified requirements. Checked
items require the evidence recorded in quickstart.md; they do not establish live-service,
hardware acceptance or full review readiness.

### Source Code (repository root)

```text
src/reachy_mini_conversation_app/
  huggingface_realtime.py       shared orchestration/events and HF implementation
  gemini_realtime.py            new Gemini transport and wire validation
  conversation_handler.py      existing public contract; minimal lifecycle additions
  config.py                    provider defaults/environment normalization
  settings_store.py            saved provider/model/voice overrides
  startup_settings.py          preserve legacy HF startup voice
  main.py                      existing handler factory selects provider
  console.py                   owns logical-session state, recovery scheduler, switches
  prompts.py                   existing instructions and memory injection
  audio/resampling.py          new stateful device-rate conversion
  static/js/views/settings.js  provider controls and memory disclosure
  static/js/api.js              existing RPC client extensions
  tools/                       existing implementations reused
  memory/                      existing store reused
tests/
  test_gemini_realtime.py       new fake-wire behavior suite
  test_console.py              lifecycle/RPC regression coverage
  test_settings_store.py       additive settings and precedence
  test_startup_settings.py     legacy voice semantics
  audio/test_resampling.py     rate, continuity, duration, reset
```

**Structure Decision**: Extend the current package and mirrored tests. Source paths describe
planned changes, not files created here. Reuse the existing HF test coverage rather than
creating duplicate suites; confirm exact test names during task generation.

## Phase 0: Research Decisions

See [research.md](research.md). Protocol, lifecycle, audio conversion, tool mapping, memory
refresh, settings migration, and dependency ownership are resolved as design choices.
Account eligibility, wheel availability on target hardware, measured quality, and full gate
health remain validation prerequisites rather than claims of success.

## Phase 1: Design

### Shared orchestration

Retain ConversationHandler as the app boundary. Extract only behavior used by both providers
from HuggingFaceRealtimeHandler into a shared handler in huggingface_realtime.py: playback
epochs, VAD, activity/transcripts, validated tool execution, late-event suppression,
prompt/memory assembly, and lifecycle bookkeeping. Both providers use this implementation.
Keep HF wire events, session.update, response.create, and native-rate extensions in the HF
implementation. Gemini must not inherit HF protocol assumptions. Keep public HF construction
working. Use a narrow typed event/transport contract, not a provider plugin framework.

### Selection, credentials, and voices

Provider IDs are huggingface and gemini. Add optional provider and Gemini model/voice
fields to AppSettings; preserve HF voice storage and resolution. Missing selection defaults
to HF; saved settings win over environment defaults. Preserve old HF startup voice and profile files, never interpreting
a saved HF voice as a Gemini voice. Configurable Gemini defaults: gemini-3.8-live and Kore;
verify account access at setup. The standard Live model is the initial supported path.
Gemini voice order is saved Gemini override, compatible personality voice, GEMINI_VOICE,
then Kore. Without an override, an incompatible personality voice blocks startup with a
valid-override prompt rather than falling through. A saved Gemini override wins even when
the profile voice is incompatible. Preserve existing HF voice resolution and legacy HF
startup voice; do not add an HF override that changes that behavior.

New environment names: REACHY_MINI_CONVERSATION_BACKEND, GEMINI_API_KEY, GEMINI_MODEL,
GEMINI_VOICE. Do not revive obsolete BACKEND_PROVIDER/MODEL_NAME. Use existing private
environment loading for keys; no credential value in RPC or settings.json. Extend
backend.config/status.get and add backend.retry. See [selection contract](contracts/backend-selection.md).

### Switching and continuity

LocalStream owns a typed RealtimeSessionState defined in huggingface_realtime.py and passes
that same object through the existing handler factory into every replacement handler for
one logical conversation. It contains provider/configuration identity, monotonically
increasing connection generation, resumption eligibility/handle, tool invocation ledger,
and safe context status. Handlers own sockets/tasks/queues, never the lifetime of this object.
Handler shutdown closes transport without erasing retained logical state. LocalStream alone
invalidates/disposes state for provider/setup changes, shutdown, or an explicitly fresh session.

Serialize all starts, reconnects, Retry clicks, and provider selections through one LocalStream
scheduler. Allocate a new generation before closing the old connection; validate ownership
before every event/action. Stop old input/output before new setup. Pass retained state to
the new handler only for same-provider, same-configuration recovery. A valid handle attempts
resume; invalid/rejected/nonresumable state is discarded and a fresh session is visibly started.
Never resume stale memory instructions. Known pending actions are reconciled through the
retained ledger without repeating their effects; uncertain outcomes are reported once.

Both providers automatically retry recoverable failures indefinitely, with delays
1, 2, 4, 8, 16, 30, 30... seconds. Reset backoff after a completed exchange; do not reset it
merely because a flapping socket briefly acknowledged setup. Manual Retry interrupts the
wait and schedules one immediate same-provider attempt without spawning another worker.
Provider changes and shutdown cancel waits and invalidate obsolete attempts atomically.
No provider fallback. Move retry ownership out of nested HF startup/LocalStream retry loops
so exactly one scheduler applies the new policy; HF conversation defaults remain unchanged,
but its retry timing deliberately follows the user's newly agreed policy.

Network/connection loss, setup/send timeouts and transient service failures retry; missing or
invalid keys, invalid configuration/model/voice, denied access, and hard billing/quota
exhaustion wait for correction. Distinguish transient rate limiting from depleted quota;
retain safe actionable reasons. Unknown provider close codes wait for explicit correction/
Retry rather than guessing a permanent error is transient. GoAway warns of imminent closure
and schedules a serialized same-provider reconnect once the old generation is invalidated.

The connection plus setup acknowledgement share one monotonic 15-second deadline, including
any resumption rejection/fresh fallback within that attempt. Every audio/message send has
a 5-second deadline. Graceful close has a 5-second deadline, after which cancel its tasks
and abandon socket ownership using public transport APIs; it cannot block shutdown or a
provider switch. Configuration/status RPC remains available throughout. A new connection
starts only when the old generation cannot own input/output, even if resource cleanup is late.

Enable context compression/resumption. Changing provider/model/voice/profile/toolset or
injected-memory revision deliberately starts a fresh session and clears the old handle.
This is the app's conservative consistency policy, not a claim that Google cannot update
non-model setup during pause/resume. The 15-minute trial covers automatic resumed reconnects,
not a single-socket guarantee. Detailed contracts and failure/ownership test cases are in
[realtime-session.md](contracts/realtime-session.md).

### Audio, tools, snapshots, and memory

Send mono PCM16 input tagged with its true sample rate; Google documents input resampling.
Decode all output parts at their advertised rate, ordinarily 24 kHz. Use soxr ResampleStream
to convert to get_output_audio_samplerate() before SDK playback. Equal-rate HF output is
unchanged. Reset/discard buffered converter output on interrupt/switch; flush only at normal
audio-turn completion. LocalStream schedules using the real emitted playback rate.

Keep Gemini automatic activity detection and local VAD ducking/movement behavior. A single
ordered socket reader handles server interrupted before any media in the same message,
advances response epoch, clears playback/resampler output and enters DRAINING_INTERRUPTED_TURN.
Reject assistant audio/transcript and old-turn tool work through the following turnComplete;
only subsequent messages can start accepted output. generationComplete alone never reopens
output. Input transcription has independent ordering and is not used as an assistant boundary.

Explicit app interrupt immediately suppresses/flushes output. Since clientContent with
turnComplete=true requests generation rather than acknowledging a stop, do not use an empty
synthetic turn as a cancellation acknowledgement. Use a fresh connection with visibly fresh
context for explicit app interrupt when no correlated server interruption boundary exists;
clear resumption, invalidate the old generation, and do not replay abandoned input/actions.
Normal server-VAD barge-in retains its connection/context. Repeated interrupts coalesce into
one reset. A missing turnComplete while draining for five seconds similarly forces an
announced fresh connection; this bounds a protocol fault without permitting stale output.
Do not mix manual activity markers with automatic VAD. Test control flags bundled with
media, delayed queued audio, repeated interruption, missing boundaries, and app interrupt
after remote generation already ended. See the state-transition contract for exact ordering.

Register only effective enabled tools; map names deterministically and validate declarations
before setup. Track call IDs before execution and retain deduplication across resume. Route
calls through the existing manager, including cancellations and uncertain completion.
Nonblocking SILENT completion preserves needs_response=False. Unsupported declarations
produce a corrective setup error, not silently missing tools.

One permitted camera request sends one JPEG through realtime image input plus sanitized
result metadata. Do not put base64 images in logs/transcripts. No capture on failure/disabled
access, no periodic video source. Reuse existing prompt/memory assembly and remember/forget.
Gemini instruction refresh deliberately starts a visibly fresh session and invalidates
handles to avoid restoring stale instructions. Global memory controls injection; disabling remember/forget tools alone
does not disable recall. Turning global memory off preserves stored facts.

### Validation and documentation

Preserve HF behavior with fake-session regressions before extracting shared code. Add Gemini
tests for setup, multipart messages, transcripts, PCM conversion, interruption, tool permissions,
silent responses, replay/cancellation, snapshots, and memory/configuration refresh. Cover
RPC compatibility, switch races, Gemini voice precedence with HF behavior unchanged,
15/5/5-second deadlines, at least ten automatic attempts, and cancellation during backoff.
Hardware validation follows [quickstart.md](quickstart.md); no mocked result proves robot quality.

Implementation updates root README and applicable root/packaged .env.example configuration
sources. Flag diagram regeneration from docs/scheme.mmd for the eventual human-authored PR;
never hand-edit generated SVG or add another README. This plan changes no source or dependencies.

### Requirement coverage

| Requirements | Design and validation |
| --- | --- |
| FR-001, FR-002, FR-007, FR-013, FR-016, FR-017 | Selection contract; settings/RPC regressions and setup-failure trials |
| FR-003, FR-004 | Shared events/audio/VAD; transcript, multipart, interrupt and robot trials |
| FR-005, FR-006, FR-011 | Tool contract/ledger; permissions, silent completion, cancellation and replay tests |
| FR-008, FR-009, FR-010 | LocalStream-owned resumable state and automatic recovery; switch races and resume/fresh tests |
| FR-012 | Environment-only credentials, redaction, no new retention; log/status/history isolation tests |
| FR-014 | Single-request image path; camera permission/failure and hardware observation trials |
| FR-015 | Existing shared memory and fresh instruction refresh; cross-provider save/recall/delete tests |

## Complexity Tracking

No constitutional exceptions requested. Constitution 2.0.0 resolves the runtime policy;
implementation must synchronize older metadata/guidance before review. Two actual transports justify the shared boundary;
device-rate playback justifies a stateful resampler. No speculative providers, new memory
storage, generic capability registry, or SDK modifications.
