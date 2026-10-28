# Tasks: Optional Gemini Conversation Backend

**Input**: Design documents from `specs/001-gemini-backend/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts](contracts/backend-selection.md),
[validation guide](quickstart.md), and `.specify/memory/constitution.md`.

**Tests**: Included because the specification defines behavioral acceptance scenarios and
measurable validation outcomes, and repository rules require feature/regression tests.
Write behavioral tests before the associated implementation; confirm expected failures
without requiring network access, a paid key, or robot hardware in the automated suite.

**Organization**: Foundation first, then user stories in priority order. This document
creates no implementation. Check a task only after its behavior and evidence are verified.

## Format: `[ID] [P?] [Story] Description`

- Tasks use sequential IDs and exact repository-relative paths.
- `[P]` identifies tasks with disjoint files that can run together once phase prerequisites pass.
- `[US1]`, `[US2]`, and `[US3]` map directly to specification stories.
- Source paths share `src/reachy_mini_conversation_app/`; paths are written fully in tasks.

## Path Conventions

Use the existing Python package and mirrored `tests/` tree. Extend existing files rather
than creating parallel settings, memory stores, README files, or app lifecycle managers.
Planning evidence belongs in this feature directory, not new Markdown under `docs/`.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify implementation prerequisites and establish the existing baseline.

- [ ] T001 Record the agreed feature issue, maintainer approach agreement, eligible personal Gemini Developer API access, and usage/data budget in `specs/001-gemini-backend/plan.md`; leave this task incomplete and do not start implementation if the required agreement is unavailable; never invent an issue number or record credentials.
- [ ] T002 Run the existing full gate and record commands, environment, and failures in `specs/001-gemini-backend/quickstart.md`; distinguish the previously observed Spec Kit lint/format and pytest setup failures from feature regressions, and route unrelated repairs separately without weakening checks or claiming review readiness.
- [ ] T003 Declare the already locked websockets dependency directly and add the previously flagged `soxr>=1.1,<2` in `pyproject.toml`, regenerate `uv.lock` with `uv lock`, and verify installation on supported desktop/Reachy platforms; preserve existing Python metadata and record unavailable platform verification in `specs/001-gemini-backend/quickstart.md` rather than assuming success.

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish a reusable, tested conversation boundary without duplicating HF behavior.

No user-story implementation begins before T001-T009 are complete. T002 may identify
separate baseline repairs, but final review remains blocked until the full gate passes.

- [ ] T004 [P] Extend fake-session regressions in `tests/test_huggingface_realtime.py` for native-rate audio, personality/greeting, transcript callbacks, tool failures, silent results, and existing HF retry/live-update behavior before extracting shared orchestration.
- [ ] T005 Define the narrow typed transport/events and session ownership in `src/reachy_mini_conversation_app/huggingface_realtime.py`, retaining the existing `src/reachy_mini_conversation_app/conversation_handler.py` public boundary; encode the data-model constraints verbatim: logical_session_id "unique string" and "Retained only across valid same-config resume", connection_generation "increasing integer" and "Changes on socket/handler replacement", response_epoch "increasing integer" and "Changes on interrupt/flush", provider "provider enum" and "Fixed per logical session", configuration_revision "integer or stable digest" and "Changes with model/voice/profile/tools/injected memory", resumption_handle "optional opaque secret" and "Memory only, never logged or exposed", and resumable "boolean" and "Most recent valid service update governs reuse"; declare attributes and avoid new Any/cast or speculative methods.
- [ ] T006 Extract only genuinely shared audio/playback, VAD, observers, prompt assembly, tool lifecycle and ownership checks into a shared handler in `src/reachy_mini_conversation_app/huggingface_realtime.py`; preserve public HuggingFaceRealtimeHandler construction and isolate HF session.update/response.create/native-rate wire behavior, proving T004 stays green.
- [ ] T007 [P] Add streaming rate-conversion behavior tests in `tests/audio/test_resampling.py` for duration/pitch-preserving 24 kHz conversion, multi-chunk continuity, equal-rate bypass, normal drain, and reset/discard on interruption; this can run alongside T004-T006 because it edits a separate file and does not depend on shared-handler implementation.
- [ ] T008 Implement the stateful soxr converter in `src/reachy_mini_conversation_app/audio/resampling.py` using the actual input/output rates, preserving filter state across chunks and dropping buffered output on reset; satisfy T007 without private SDK calls or stateless per-chunk interpolation.
- [ ] T009 Integrate device-rate conversion and ownership-tagged playback in `src/reachy_mini_conversation_app/console.py` and `src/reachy_mini_conversation_app/huggingface_realtime.py` using public get_output_audio_samplerate()/push_audio_sample(); emit the true playback rate, keep HF equal-rate behavior unchanged, and run T004/T007 plus existing `tests/test_console.py` and `tests/test_streaming.py` coverage.

**Checkpoint**: HF regressions pass; both future provider paths can share the lifecycle and
playback boundary. There is no duplicated conversation loop or speculative provider registry.

## Phase 3: User Story 1 - Choose a Provider and Talk (Priority: P1)

**Goal**: Persist explicit provider selection, configure Gemini, and conduct a personality-led
spoken conversation with transcripts while retaining HF as the untouched default.

**Independent Test**: Verify untouched HF startup with no Gemini key, then select a configured
Gemini account and complete three spoken exchanges with greeting/transcripts; restart and
verify selection and provider-specific voice/settings retention. Inject setup failures and
confirm configuration, explicit retry, and manual HF selection remain usable.

### Tests for User Story 1

- [ ] T010 [P] [US1] Add additive-settings contract tests in `tests/test_settings_store.py` for missing-provider HF default, saved-over-environment precedence, invalid persisted values, nonempty model/voice strings, provider settings isolation, and absence of keys/handles/transcripts in settings.json.
- [ ] T011 [P] [US1] Add fake Gemini setup/audio/transcript tests in `tests/test_gemini_realtime.py` for setupComplete readiness, all multipart content, real-rate PCM16 input, 24 kHz output decoding, selected personality/greeting, malformed required events, and authentication/access/model/voice/quota errors without sensitive output.
- [ ] T012 [P] [US1] Extend `tests/test_console.py` for backend.config/status.get, legacy HF-only payloads, provider-aware readiness and Retry scheduling, missing-key waiting_for_config, and responsive settings after startup failure; verify save acknowledgement is not reported as successful connection.

### Implementation for User Story 1

- [ ] T013 [US1] Add provider/config normalization in `src/reachy_mini_conversation_app/config.py` for REACHY_MINI_CONVERSATION_BACKEND, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_VOICE; enforce "Saved > environment > huggingface", "Saved > GEMINI_MODEL > gemini-3.8-live; validate supported Live path", and "Saved > GEMINI_VOICE > Kore; validate Gemini catalog"; keep obsolete BACKEND_PROVIDER/MODEL_NAME inactive and no Gemini key requirement for HF.
- [ ] T014 [US1] Extend AppSettings read/merge/runtime application in `src/reachy_mini_conversation_app/settings_store.py` with conversation_backend "optional huggingface/gemini", gemini_model/gemini_voice "optional nonempty string", hf_voice "optional nonempty string", and existing hf_* constraint "Switching never clears these"; preserve version 1, atomic updates, logged invalid saved selection fallback, and strict validation of explicit RPC selections.
- [ ] T015 [US1] Implement per-provider voice resolution across `src/reachy_mini_conversation_app/config.py`, `src/reachy_mini_conversation_app/startup_settings.py`, and `src/reachy_mini_conversation_app/console.py`; enforce hf_voice "New HF-only override; retain legacy startup/profile fallback", do not rewrite profile.md or reinterpret legacy HF voice as Gemini, surface incompatible choices with a valid correction, and extend `tests/test_startup_settings.py` for legacy persistence.
- [ ] T016 [US1] Implement Gemini Developer API TLS/header authentication, immutable setup, setup acknowledgement, audio/transcript event validation and injected greeting/text in `src/reachy_mini_conversation_app/gemini_realtime.py`; use the shared handler/events, standard configured Live model, PCM16 actual-rate input and resampled playback, process every content part, and normalize errors without logging raw frames, key-bearing URLs or secrets.
- [ ] T017 [US1] Select the concrete provider at the existing factory in `src/reachy_mini_conversation_app/main.py`, keeping imports at module scope and tool/robot dependencies shared; extend `tests/test_main.py` to prove HF default construction and Gemini selection without executing paid calls.
- [ ] T018 [US1] Extend backend.config/status.get and add basic backend.retry scheduling in `src/reachy_mini_conversation_app/console.py` per `specs/001-gemini-backend/contracts/backend-selection.md`; preserve HF payloads and status fields, reject credential parameters and invalid explicit choices, expose key-present boolean only, use "waiting_for_config, connecting, connected, disconnected, restart_required" and context_state "new/resumed/unavailable", and prevent background Gemini retries while retaining HF automatic retry.
- [ ] T019 [US1] Add provider-specific configuration and voice controls, setup errors, explicit Retry/manual selection, and shared-memory disclosure in `src/reachy_mini_conversation_app/static/js/views/settings.js` and RPC calls/reason messages in `src/reachy_mini_conversation_app/static/js/api.js`; display only relevant provider controls and no implementation details or secret-value fields.
- [ ] T020 [US1] Verify T010-T019 with fake-session/RPC suites and an available-account three-exchange trial from `specs/001-gemini-backend/quickstart.md`, recording sanitized results there; confirm persisted selection, personality/greeting/transcripts, HF unchanged without a key, and usable setup failures before calling the first increment complete.

**Checkpoint**: US1 is a voice/configuration demo increment, not release readiness. The full
feature still requires US2 tools/interruption/camera/memory and US3 continuity guarantees.

## Phase 4: User Story 2 - Interrupt and Use Robot Tools (Priority: P1)

**Goal**: Interrupt speech and execute permitted essential robot tools, snapshots, and shared
memory without breaking conversation or relaxing permissions.

**Independent Test**: Interrupt a response, request head/status and each essential action,
inject a tool error, request one snapshot, and save/recall/forget a disposable fact in both
provider directions. Verify disabled tools/global controls block their respective operations.

### Tests for User Story 2

- [ ] T021 [P] [US2] Extend `tests/test_gemini_realtime.py` with server/app interruption and late-audio suppression, partial/completed/interrupted transcripts, simultaneous function calls, aliases/collisions/schema rejection, nonblocking SILENT completion, cancellation, disabled/invalid tool arguments, and duplicate-call behavior.
- [ ] T022 [P] [US2] Extend `tests/tools/test_camera.py` and `tests/tools/test_background_tool_manager.py` for camera failure/disabled capture, cancellable versus already-started work, and error results that leave subsequent conversation usable; reuse SDK media and existing manager semantics.
- [ ] T023 [P] [US2] Extend `tests/test_memory_routes.py` for cross-provider saved-memory recall and deletion, memory-operation failures, fresh Gemini instruction refresh, global memory disabled without deleting facts, and the distinction between global injection control and remember/forget tool permissions.

### Implementation for User Story 2

- [ ] T024 [US2] Connect server interruption and explicit app interrupt to shared playback flush, remote terminating turn and response epoch in `src/reachy_mini_conversation_app/huggingface_realtime.py` and `src/reachy_mini_conversation_app/gemini_realtime.py`; retain automatic Gemini VAD/local ducking without manual activity markers, and suppress old-turn output until a valid new turn boundary.
- [ ] T025 [US2] Convert only effective enabled tool specs in `src/reachy_mini_conversation_app/gemini_realtime.py`, enforcing "letters, digits, underscore, dash; maximum 128 characters", deterministic collision-free reverse aliases and supported parametersJsonSchema; fail setup with corrective tool_schema_unsupported rather than silently losing capabilities.
- [ ] T026 [US2] Implement in-memory invocation ownership/deduplication in `src/reachy_mini_conversation_app/huggingface_realtime.py` with key "logical_session_id plus provider call_id", states "received/running/completed/cancelled/uncertain", and "Register before execution"; never automatically repeat uncertain/dispatched work, never persist the ledger, and do not evict IDs in a way that enables replay within a live logical session.
- [ ] T027 [US2] Route every Gemini functionCalls/cancellation entry and functionResponses ID through existing BackgroundToolManager in `src/reachy_mini_conversation_app/gemini_realtime.py` and shared completion handling in `src/reachy_mini_conversation_app/huggingface_realtime.py`; preserve enabled head, volume, status, dance/stop and sleep behavior, operational error dictionaries, app-local idle work, and needs_response=False nonblocking SILENT results.
- [ ] T028 [US2] Adapt the existing camera result in `src/reachy_mini_conversation_app/gemini_realtime.py` to sanitized function metadata plus exactly one image/jpeg realtime input; enforce tool/global/--no-camera controls, omit b64_im from text/log/transcript, send no image on failure, and never recapture or stream continuously after send failure.
- [ ] T029 [US2] Reuse `src/reachy_mini_conversation_app/prompts.py`, existing remember/forget operations and `src/reachy_mini_conversation_app/memory_routes.py` refresh callbacks in the shared/Gemini handlers; refresh immutable Gemini instructions with a visibly fresh session and invalidated handle, preserve existing saved-memory IDs/retention/deletion, and expose failed operations without false success claims.
- [ ] T030 [US2] Carry explicit interrupted-fragment metadata through `src/reachy_mini_conversation_app/conversation_handler.py`, `src/reachy_mini_conversation_app/console.py`, and `src/reachy_mini_conversation_app/static/js/components/conversation-panel.js`; retain existing observer compatibility and transcript retention, and do not label abandoned assistant fragments as completed utterances.
- [ ] T031 [US2] Run the US2 suites and independent tool/camera/memory/interruption trials in `specs/001-gemini-backend/quickstart.md`, recording sanitized evidence for SC-003/SC-004/SC-009/SC-010/SC-011; test sleep separately and relaunch, verify failures permit the next spoken exchange, and leave hardware-dependent evidence incomplete when hardware is unavailable.

**Checkpoint**: Voice, interruption, essential actions, on-demand vision and shared memories
work under existing permissions. Recovery during active work remains the focus of US3.

## Phase 5: User Story 3 - Switch and Recover Predictably (Priority: P2)

**Goal**: Serialize switches, prevent stale-session effects, and offer explicit Gemini
retry with truthful resumed/fresh context and no duplicate robot actions.

**Independent Test**: Switch both ways during speech/action execution, inject disconnects,
exercise valid and rejected resumption, and confirm late old-session output never reaches
the current conversation. Repeat rapid selections/retries and verify one active connection.

### Tests for User Story 3

- [ ] T032 [P] [US3] Extend `tests/test_console.py` for rapid provider-selection races, retry coalescing, old-input/output suppression, one active handler, preserved HF auto-retry versus Gemini manual-only recovery, and visible fresh/resumed status without live-history transfer.
- [ ] T033 [P] [US3] Extend `tests/test_gemini_realtime.py` for GoAway, valid/invalid/resumable=false handles, resume rejection, profile/model/voice/toolset/memory revision changes, duplicate calls across resume, late tool completion/cancellation and uncertain actions, with no background reconnect.

### Implementation for User Story 3

- [ ] T034 [US3] Serialize provider/configuration transitions in `src/reachy_mini_conversation_app/console.py` using the existing restart lifecycle, marking the old generation inactive before flushing and shutting down, honoring the latest confirmed selection, and preserving other-provider settings and shared memories without transferring live history.
- [ ] T035 [US3] Enforce generation/session/response ownership at audio enqueue, microphone send, observer callbacks, image submission and tool dispatch/completion in `src/reachy_mini_conversation_app/huggingface_realtime.py` and `src/reachy_mini_conversation_app/console.py`; discard disconnected microphone input and old queued work, and preserve existing cancellation semantics for already-started physical actions.
- [ ] T036 [US3] Complete provider-specific readiness/retry/shutdown handling in `src/reachy_mini_conversation_app/console.py`, ensuring Gemini waits for explicit Retry or selection after failure/close, repeated requests cannot create parallel sockets, configuration remains usable, and HF's existing automatic recovery remains unchanged.
- [ ] T037 [US3] Implement Gemini contextWindowCompression/sessionResumption updates, GoAway warning and explicit-retry resume in `src/reachy_mini_conversation_app/gemini_realtime.py`; keep handles "Memory only, never logged or exposed", clear them on configuration_revision changes, and visibly start fresh when continuity is unavailable or rejected without provider fallback.
- [ ] T038 [US3] Reconcile the invocation ledger across same-logical-session resume in `src/reachy_mini_conversation_app/huggingface_realtime.py` and `src/reachy_mini_conversation_app/gemini_realtime.py`; rebind only known valid origin calls, report uncertain completion without retry, optionally resubmit a known result only for the same resumed call, and discard all old queues on a fresh session.
- [ ] T039 [US3] Display GoAway/disconnection, actionable errors, fresh versus resumed context and uncertain-action feedback in `src/reachy_mini_conversation_app/static/js/views/settings.js` and `src/reachy_mini_conversation_app/static/js/components/conversation-panel.js`, using safe existing status/RPC output without displaying handles or silently claiming continuity.
- [ ] T040 [US3] Execute the US3 suites and ten-switch/disconnect/recovery scenarios in `specs/001-gemini-backend/quickstart.md`, recording SC-005/SC-006/SC-007 evidence; verify provider/profile/voice/toolset/memory changes invalidate stale handles and unknown-completion robot actions never replay.

**Checkpoint**: All three stories can be demonstrated individually using the shared
foundation and earlier integrated increments; none requires unavailable later-story work.

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Complete documentation, cross-platform checks and end-to-end evidence.

- [ ] T041 [P] Update the existing root `README.md` with Gemini setup, provider/voice selection, retry/fresh-session boundaries, personal Developer API scope, on-demand camera/shared-memory disclosure, and explicit exclusions; do not add another README or rewrite protected contribution files.
- [ ] T042 [P] Document REACHY_MINI_CONVERSATION_BACKEND, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_VOICE and precedence in `.env.example`; check the existing packaging mapping in `setup.py`/`MANIFEST.in` to ensure packaged defaults receive the same example, without introducing a redundant source file or committing a private .env.
- [ ] T043 [P] Record the architecture-diagram update requirement for the future human-authored PR in `specs/001-gemini-backend/quickstart.md`, referencing `docs/scheme.mmd` and generated `docs/assets/conversation_app_arch.svg`; do not hand-edit SVG or create Markdown under docs/.
- [ ] T044 Extend redaction/retention tests in `tests/test_gemini_realtime.py` and `tests/test_console.py` to prove failures/status/debug logging cannot expose keys, handles, raw image data or prior-provider live history; review shared-module changes for narrow logged exceptions, typed public signatures, and no new suppressions.
- [ ] T045 Run the complete Ruff/format/mypy/pytest gate and `uv lock --check` against `pyproject.toml`, `uv.lock`, `src/`, and `tests/`, recording final results in `specs/001-gemini-backend/quickstart.md`; require all checks green before review and preserve supported-platform compatibility without CI workflow edits.
- [ ] T046 Complete the 15-minute/10-exchange real-robot validation and all remaining SC-001 through SC-011 evidence in `specs/001-gemini-backend/quickstart.md`, including explicit Retry across service limits, 9/10 sub-second recognized interruptions, camera failure/permissions, memory in both provider directions, and device sample rates; do not substitute mocks for hardware acceptance or fabricate unavailable measurements.
- [ ] T047 Self-review the focused diff against `specs/001-gemini-backend/spec.md`, `specs/001-gemini-backend/plan.md`, and `AGENTS.md`, ensure no secrets or unrelated changes, and leave human review/PR creation to the developer using the existing `.github/pull_request_template.md` without modifying that template.

## Dependencies & Execution Order

### Phase Dependencies

```text
T001 agreement -> T002 baseline -> T003 dependencies
  -> Foundation T004-T009
  -> US1 T010-T020
  -> US2 T021-T031
  -> US3 T032-T040
  -> Polish T041-T047
```

T004 and T007 can proceed together after Setup. T005 follows T004; T006 follows T005.
T008 follows T007; T009 requires both T006 and T008. All story tests may be authored in the
parallel groups below, then implementation proceeds in ID order. Later tasks in the same
files are intentionally not marked parallel. T045 follows T041-T044; T046 follows T045;
T047 follows complete validation. Hardware trials require their respective story implementation.

### User Story Dependencies

- US1 depends on Foundation and is independently testable as voice/configuration MVP.
- US2 depends on the integrated US1 conversation path. It is independently verifiable as
  a tool/vision/memory increment, not falsely advertised as implementation-independent.
- US3 depends on US1 and US2 ownership/tool behavior. It adds switching-under-load and
  continuity validation, rather than duplicating basic Retry/setup work from US1.
- This small shared codebase has deliberate sequential story integration; do not run
  whole stories concurrently against shared realtime/console modules.

### Within Each User Story

Tests precede implementation and demonstrate meaningful failing behavior. Implement
settings/types before transport/factory/RPC integration and then UI. Verify each checkpoint
before the next increment. Task generation does not run any implementation task.

### Parallel Opportunities

- Foundation: T004 HF tests and T007 audio tests use different files.
- US1: T010 settings, T011 Gemini protocol, and T012 console contract tests are disjoint.
- US2: T021 Gemini tests, T022 camera/manager tests, and T023 memory-route tests are disjoint.
- US3: T032 console tests and T033 Gemini recovery tests are disjoint.
- Polish: T041 README, T042 environment examples, and T043 diagram review note are disjoint.

## Parallel Example: User Story 1

After T009, author T010 in tests/test_settings_store.py, T011 in
tests/test_gemini_realtime.py, and T012 in tests/test_console.py together. Do not implement
T013-T019 until their tests/contracts are understood; integrate in order because files overlap.

## Parallel Example: User Story 2

After T020, author T021 protocol tests, T022 camera/manager tests, and T023 memory-route
tests together. Then implement T024-T030 sequentially; these share handlers and lifecycle state.

## Parallel Example: User Story 3

After T031, author T032 switch/RPC tests and T033 resume/cancellation tests together.
Then integrate T034-T039 sequentially to preserve one consistent ownership model.

## Implementation Strategy

### MVP First (User Story 1 Only)

Complete Setup/Foundation and US1, then run T020. This yields a bounded internal voice
demo with provider configuration, setup failures and transcripts. It does not satisfy the
full requested release, which includes tools, interruption, camera, memory and continuity.

### Incremental Delivery

Add US2 and verify T031; add US3 and verify T040. Retest HF after each shared change. Finish
documentation and the full gate, then hardware acceptance. Keep tasks with unavailable human,
service or hardware prerequisites unchecked and report the specific missing evidence.

### Parallel Team Strategy

Use only the disjoint groups above after their predecessors complete; no parallel writes
to shared handler/console modules. These examples describe scheduling opportunities and do
not authorize spawning agents or external actions during implementation.

## Notes

All 17 functional requirements map to concrete tasks: FR-001/002/007/013/016/017 to US1;
FR-003 to US1 and US2 transcripts; FR-004/005/006/014/015 to US2; FR-008/009/010/011 to US3
and US2 deduplication; FR-012 to settings isolation, redaction, and final review. All success
criteria are covered by story validations and T046. No generic cleanup or unrelated refactor
is authorized by this task list.
