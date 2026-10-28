# Implementation Plan: Optional Gemini Conversation Backend

**Branch**: `feat/add-gemini-backend` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-gemini-backend/spec.md`

## Summary

Add Gemini Developer API as an explicit optional provider, retaining Hugging Face as default.
Support voice, interruption, transcripts, essential tools, on-demand snapshots, and shared
memory. Keep shared orchestration in `huggingface_realtime.py`; isolate Gemini wire messages
in `gemini_realtime.py`. Extend existing settings, handler factory, RPC, and restart UI.

## Technical Context

**Language/Version**: Existing metadata requires Python >=3.11; new syntax remains compatible
with the contribution rules' Python 3.10 constraint. Strict mypy targets 3.12. Preserve runtime
metadata; the existing metadata/governance mismatch is not changed in this feature.

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
one second in 9/10 trials, ten clean switches, and no replayed actions. These are unmeasured targets.

**Constraints**: One active provider, manual Gemini recovery, immutable Gemini setup,
provider-specific voices, 24 kHz Gemini output, no continuous video, shared memory under
existing controls, and no live-history transfer between providers or credential exposure.

**Scale/Scope**: One robot, two providers, one active conversation. This command ends at design.

## Constitution Check

*GATE: Evaluated before research and rechecked after design.*

| Gate | Before research | After design |
| --- | --- | --- |
| SDK public API only | Pass: existing media/tool APIs | Pass: public audio/sample-rate APIs |
| Shared behavior in realtime module | Pass: no second app loop | Pass: shared handler in huggingface_realtime.py |
| Focused minimal change | Pass: one optional backend | Pass: two transports, no registry/new database |
| Typed boundaries and graceful errors | Pass: required by spec | Pass: validated wire events, errors, ownership |
| Essential tests | Pass: behavior scenarios defined | Pass: HF regression, protocol, lifecycle, robot matrix |
| Dependency changes flagged | Pass: none added | Pass: websockets ownership and soxr flagged |
| Documentation and diagram | Pass: protected files unchanged | Pass: root README/env updates and diagram flag planned |

No unjustified constitutional exception is proposed. Implementation remains gated on an
agreed issue and approach, eligible account access, usage/data budget, and green repository
checks. No issue number is known: do not invent one or interpret planning as bypassing this
requirement. The constitution ratification-date TODO is a separate governance follow-up.

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

tasks.md belongs to the subsequent speckit-tasks phase and is not created here.

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
  console.py                   readiness/status/retry/switch lifecycle
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

Provider IDs are huggingface and gemini. Add optional provider, Gemini model/voice, and HF
voice override fields to AppSettings. Missing selection defaults to HF; saved settings win
over environment defaults. Preserve old HF startup voice and profile files, never interpreting
a saved HF voice as a Gemini voice. Configurable Gemini defaults: gemini-3.8-live and Kore;
verify account access at setup. The standard Live model is the initial supported path.

New environment names: REACHY_MINI_CONVERSATION_BACKEND, GEMINI_API_KEY, GEMINI_MODEL,
GEMINI_VOICE. Do not revive obsolete BACKEND_PROVIDER/MODEL_NAME. Use existing private
environment loading for keys; no credential value in RPC or settings.json. Extend
backend.config/status.get and add backend.retry. See [selection contract](contracts/backend-selection.md).

### Switching and continuity

Serialize transitions through LocalStream's existing restart mechanism. Invalidate the old
generation before flushing playback and shutting down; then construct the selected handler.
Reject late callbacks and old tool requests. Already executing motions follow existing
cancellation behavior: cancelling a task does not undo physical effects.

Gemini failures await explicit Retry/selection. Preserve HF automatic retries under
FR-002/SC-001; the new manual-recovery assumption applies to Gemini, not a redesign of HF.
If manual-only HF behavior is intended, clarify the spec before changing that path.

Enable compression/resumption. GoAway warns of closure; closure waits for manual Retry.
Retry can use a valid same-config in-memory handle and retained call ledger. Invalid/rejected
resume visibly starts fresh as part of that retry. Provider/model/voice/profile/toolset or
injected-memory changes invalidate the handle and visibly start fresh. No automatic fallback
or hidden background Gemini reconnect. The 15-minute trial may span explicit resumed connections.

### Audio, tools, snapshots, and memory

Send mono PCM16 input tagged with its true sample rate; Google documents input resampling.
Decode all output parts at their advertised rate, ordinarily 24 kHz. Use soxr ResampleStream
to convert to get_output_audio_samplerate() before SDK playback. Equal-rate HF output is
unchanged. Reset/discard buffered converter output on interrupt/switch; flush only at normal
audio-turn completion. LocalStream schedules using the real emitted playback rate.

Keep Gemini automatic activity detection and existing local VAD ducking/movement behavior.
Server interruption confirms flush. Explicit app interrupt sends a documented terminating
client turn and advances the response epoch; late old-turn output stays suppressed. Do not
mix manual activityStart/activityEnd with automatic VAD. Verify this boundary in fake-wire
and hardware tests; local queue clearing alone does not establish remote cancellation.

Register only effective enabled tools; map names deterministically and validate declarations
before setup. Track call IDs before execution and retain deduplication across resume. Route
calls through the existing manager, including cancellations and uncertain completion.
Nonblocking SILENT completion preserves needs_response=False. Unsupported declarations
produce a corrective setup error, not silently missing tools.

One permitted camera request sends one JPEG through realtime image input plus sanitized
result metadata. Do not put base64 images in logs/transcripts. No capture on failure/disabled
access, no periodic video source. Reuse existing prompt/memory assembly and remember/forget.
Gemini instruction refresh starts a visibly fresh session and invalidates handles because
setup is immutable. Global memory controls injection; disabling remember/forget tools alone
does not disable recall. Turning global memory off preserves stored facts.

### Validation and documentation

Preserve HF behavior with fake-session regressions before extracting shared code. Add Gemini
tests for setup, multipart messages, transcripts, PCM conversion, interruption, tool permissions,
silent responses, replay/cancellation, snapshots, and memory/configuration refresh. Cover
RPC compatibility, switch races, per-provider voices, setup failures and manual retry.
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
| FR-008, FR-009, FR-010 | Session ownership/manual Gemini recovery; switch races and resume/fresh tests |
| FR-012 | Environment-only credentials, redaction, no new retention; log/status/history isolation tests |
| FR-014 | Single-request image path; camera permission/failure and hardware observation trials |
| FR-015 | Existing shared memory and fresh instruction refresh; cross-provider save/recall/delete tests |

## Complexity Tracking

No constitutional exceptions requested. Two actual transports justify the shared boundary;
device-rate playback justifies a stateful resampler. No speculative providers, new memory
storage, generic capability registry, or SDK modifications.
