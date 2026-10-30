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
creates no implementation. This regeneration supersedes the original manual-Gemini and
older-runtime tasks. Check a task only after its behavior and evidence are verified.

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

- [X] T001 Record the user-approved personal customization scope in `specs/001-gemini-backend/plan.md`: local implementation and simulated tests are authorized without an upstream Issue or maintainer approval; paid API calls, account eligibility, usage/data budget and physical robot validation remain deferred and must not be claimed complete.
- [X] T002 Run the existing full gate and record commands, environment, and failures in `specs/001-gemini-backend/quickstart.md`; distinguish the previously observed Spec Kit lint/format and pytest setup failures from feature regressions, and route unrelated repairs separately without weakening checks or claiming review readiness.
- [X] T003 Set requires-python to >=3.12, declare the already locked websockets dependency directly and add the previously flagged `soxr>=1.1,<2` in `pyproject.toml`, regenerate `uv.lock` with `uv lock`, and validate a clean Python 3.12 install on supported desktop/Reachy platforms; align superseded runtime statements in `AGENTS.md` and `README.md` with constitution 2.0.0 without weakening remaining style rules or editing protected CI/contribution files; record unavailable platform checks in `specs/001-gemini-backend/quickstart.md` rather than claiming they passed.

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish a reusable, tested conversation boundary without duplicating HF behavior.

No user-story implementation begins before T001-T009 are complete. T002 may identify
separate baseline repairs, but final review remains blocked until the full gate passes.

- [X] T004 [P] Extend fake-session regressions in `tests/test_huggingface_realtime.py` for native-rate audio, personality/greeting, transcript callbacks, tool failures, silent results and HF wire/live-update behavior before extracting orchestration; preserve HF provider/voice defaults while allowing retry timing to change under the newly agreed common policy.
- [X] T005 Define RealtimeSessionState and narrow typed transport/events in `src/reachy_mini_conversation_app/huggingface_realtime.py`, retaining the `src/reachy_mini_conversation_app/conversation_handler.py` boundary; quote and encode data-model constraints: logical_session_id "unique string" / "Retained only across valid same-config resume", connection_generation "increasing integer" / "Changes on socket/handler replacement", response_epoch "increasing integer" / "Changes on interrupt/flush", provider "provider enum" / "Fixed per logical session", configuration_revision "integer or stable digest" / "Changes with model/voice/profile/tools/injected memory", resumption_handle "optional opaque secret" / "Memory only, never logged or exposed", resumable "boolean" / "Most recent valid service update governs reuse", state "waiting_for_config, connecting, connected, disconnected, restart_required; retry wait is disconnected plus retry metadata", and context_state "new/resumed/unavailable"; avoid Any/cast, undeclared attributes and speculative methods.
- [X] T006 Extract genuinely shared audio/playback, VAD, observer, prompt and tool-lifecycle behavior into a shared handler in `src/reachy_mini_conversation_app/huggingface_realtime.py`; preserve public HF construction, separate HF wire/session.update/response.create/native-rate behavior, make one transport attempt return control to LocalStream rather than own nested retry loops, and keep T004 regressions green.
- [X] T007 [P] Add streaming rate-conversion behavior tests in `tests/audio/test_resampling.py` for duration/pitch-preserving 24 kHz conversion, multi-chunk continuity, equal-rate bypass, normal drain, and reset/discard on interruption; this can run alongside T004-T006 because it edits a separate file and does not depend on shared-handler implementation.
- [X] T008 Implement the stateful soxr converter in `src/reachy_mini_conversation_app/audio/resampling.py` using the actual input/output rates, preserving filter state across chunks and dropping buffered output on reset; satisfy T007 without private SDK calls or stateless per-chunk interpolation.
- [X] T009 Make LocalStream the sole owner of RealtimeSessionState and an application-lifetime generation counter in `src/reachy_mini_conversation_app/console.py`, pass the same state reference through the existing factory in `src/reachy_mini_conversation_app/main.py` into replacement handlers, and ensure transport shutdown never erases owner state; integrate public SDK sample-rate playback with epoch/generation checks and the T008 converter, retaining HF equal-rate behavior and passing `tests/test_huggingface_realtime.py`, `tests/test_console.py`, `tests/test_streaming.py` and `tests/audio/test_resampling.py`.

**Checkpoint**: HF regressions pass; both future provider paths can share the lifecycle and
playback boundary. There is no duplicated conversation loop or speculative provider registry.

## Phase 3: User Story 1 - Choose a Provider and Talk (Priority: P1)

**Goal**: Persist explicit provider selection, configure Gemini, and conduct a personality-led
spoken conversation with transcripts while retaining HF as default and implementing the
agreed automatic recovery policy for both providers.

**Independent Test**: Verify untouched HF startup with no Gemini key, then select a configured
Gemini account and complete three spoken exchanges with greeting/transcripts; restart and
verify selection and provider-specific voice/settings retention. Inject setup failures and
confirm correct voice precedence, bounded setup failures, automatic retry, manual Retry and
manual provider selection remain usable.

### Tests for User Story 1

- [X] T010 [P] [US1] Add additive-settings contract tests in `tests/test_settings_store.py` for missing-provider HF default, saved-over-environment precedence, invalid persisted values, nonempty model/voice strings, provider settings isolation, and absence of keys/handles/transcripts in settings.json.
- [X] T011 [P] [US1] Add fake Gemini setup/audio/transcript tests in `tests/test_gemini_realtime.py` for setupComplete readiness, multipart content, actual-rate PCM16 input, 24 kHz output, personality/greeting, malformed required events and normalized authentication/access/model/voice/quota failures; include silent setup and blocked-send fake-clock tests for the shared 15-second connection/setup deadline and 5-second send deadline, with no sensitive output.
- [X] T012 [P] [US1] Extend `tests/test_console.py` for backend.config/status.get, legacy HF payloads, provider-aware readiness, key-missing waiting_for_config, manual-Retry coalescing and safe status metadata; use a fake clock to prove both providers retry recoverable failures at 1/2/4/8/16/30... seconds for at least ten attempts, reset only after a completed exchange, wait on permanent configuration/authentication failures, and keep configuration/manual selection usable.

### Implementation for User Story 1

- [X] T013 [US1] Add provider/environment normalization in `src/reachy_mini_conversation_app/config.py` for REACHY_MINI_CONVERSATION_BACKEND, GEMINI_API_KEY, GEMINI_MODEL and GEMINI_VOICE; enforce "Saved > environment > huggingface", "Saved > GEMINI_MODEL > gemini-3.8-live; validate supported Live path", and "Saved > compatible personality voice > GEMINI_VOICE > Kore; validate Gemini catalog"; retain obsolete BACKEND_PROVIDER/MODEL_NAME inactivity, standard Live model scope and no Gemini key requirement for HF.
- [X] T014 [US1] Extend AppSettings read/merge/runtime application in `src/reachy_mini_conversation_app/settings_store.py` with conversation_backend "optional huggingface/gemini", gemini_model/gemini_voice "optional nonempty string", and existing hf_* constraint "Switching never clears these"; preserve version 1, atomic updates, logged invalid saved-provider fallback and strict explicit request validation; add no new HF voice override or credential/token persistence.
- [X] T015 [US1] Implement Gemini voice resolution in `src/reachy_mini_conversation_app/config.py`, `src/reachy_mini_conversation_app/prompts.py` and `src/reachy_mini_conversation_app/console.py` with saved Gemini override, compatible personality voice, environment, then Kore; absent override plus incompatible profile voice requires a valid override instead of fallthrough, while a saved override bypasses incompatibility; preserve `src/reachy_mini_conversation_app/startup_settings.py` HF resolution/storage and profile.md, and extend `tests/test_startup_settings.py` for unchanged legacy behavior and override isolation.
- [X] T016 [US1] Implement Gemini Developer API TLS/header authentication, initial setup, acknowledgement, multipart audio/transcript validation and greeting/text injection in `src/reachy_mini_conversation_app/gemini_realtime.py`; use shared state/events and PCM16 true-rate input/resampled output, enforce one 15-second budget across connection/setup and 5 seconds per send, and classify transient versus permanent failures without logging raw frames, keys, handles or credential-bearing URLs.
- [X] T017 [US1] Select HF or Gemini in the existing factory in `src/reachy_mini_conversation_app/main.py`, passing the LocalStream-owned state from T009 rather than allocating replacement-handler-local state; keep imports at module scope and robot/tool dependencies shared; extend `tests/test_main.py` for HF default, Gemini selection and state-reference preservation without paid calls.
- [X] T018 [US1] Extend backend.config/status.get/backend.retry in `src/reachy_mini_conversation_app/console.py` per `specs/001-gemini-backend/contracts/backend-selection.md` and implement one LocalStream recovery scheduler for both providers: indefinite 1/2/4/8/16/30... second waits, reset after a completed exchange, one immediate manual-Retry attempt, coalesced clicks, 15/5/5-second setup/send/close deadlines, and cancellation on switch/shutdown; await correction for invalid credentials/configuration, denied access and hard billing/quota errors, distinguish transient rate limits, eliminate nested retries, preserve HF request/status compatibility, reject key parameters and expose only safe readiness/context/retry metadata.
- [X] T019 [US1] Add provider/voice controls, setup errors, automatic-recovery status, manual Retry/selection and shared-memory disclosure in `src/reachy_mini_conversation_app/static/js/views/settings.js` and RPC calls/reason messages in `src/reachy_mini_conversation_app/static/js/api.js`; display only relevant controls, preserve HF voice behavior, and show neither secret fields nor implementation details.
- [X] T020 [US1] Verify T010-T019 with fake-session/RPC suites and the available-account three-exchange trial from `specs/001-gemini-backend/quickstart.md`; record persisted selection, correct personality/greeting/transcripts, Gemini voice precedence, unchanged HF defaults without a key, bounded setup failures and automatic recovery for both providers, keeping unavailable live evidence incomplete.

**Checkpoint**: US1 is a voice/configuration demo increment, not release readiness. The full
feature still requires US2 tools/interruption/camera/memory and US3 continuity guarantees.

## Phase 4: User Story 2 - Interrupt and Use Robot Tools (Priority: P1)

**Goal**: Interrupt speech and execute permitted essential robot tools, snapshots, and shared
memory without breaking conversation or relaxing permissions.

**Independent Test**: Interrupt a response, request head/status and each essential action,
inject a tool error, request one snapshot, and save/recall/forget a disposable fact in both
provider directions. Verify disabled tools/global controls block their respective operations.

### Tests for User Story 2

- [X] T021 [P] [US2] Extend `tests/test_gemini_realtime.py` for ordered interrupted/turnComplete barriers, both flags in one message, media bundled with interrupted, delayed old-epoch audio, generationComplete alone, independently ordered input transcripts, repeated/missing barriers and app interrupt after generation ended; also cover aliases/schema rejection, simultaneous functions, nonblocking SILENT results, permissions/argument errors, cancellation and duplicate calls.
- [X] T022 [P] [US2] Extend `tests/tools/test_camera.py` and `tests/tools/test_background_tool_manager.py` for camera failure/disabled capture, cancellable versus already-started work, and error results that leave subsequent conversation usable; reuse SDK media and existing manager semantics.
- [X] T023 [P] [US2] Extend `tests/test_memory_routes.py` for cross-provider saved-memory recall and deletion, memory-operation failures, fresh Gemini instruction refresh, global memory disabled without deleting facts, and the distinction between global injection control and remember/forget tool permissions.

### Implementation for User Story 2

- [X] T024 [US2] Implement ACCEPTING/DRAINING_INTERRUPTED_TURN in `src/reachy_mini_conversation_app/gemini_realtime.py` and shared flush/epoch handling in `src/reachy_mini_conversation_app/huggingface_realtime.py`: tag events at ordered receipt, process interrupted before bundled media, discard abandoned envelope/output through following turnComplete, and reopen only subsequent messages, never generationComplete alone; preserve input transcript/control processing, avoid routing server barge-in through public app-interrupt reset, and serialize an announced fresh connection with cleared handle for an uncorrelated explicit app interrupt or five-second missing barrier, coalescing repeated resets without synthetic stop-only turns.
- [X] T025 [US2] Convert only effective enabled tool specs in `src/reachy_mini_conversation_app/gemini_realtime.py`, enforcing "letters, digits, underscore, dash; maximum 128 characters", deterministic collision-free reverse aliases and supported parametersJsonSchema; fail setup with corrective tool_schema_unsupported rather than silently losing capabilities.
- [X] T026 [US2] Implement invocation deduplication in the LocalStream-owned RealtimeSessionState defined in `src/reachy_mini_conversation_app/huggingface_realtime.py`, with key "logical_session_id plus provider call_id", states "received/running/completed/cancelled/uncertain", and "Register before execution"; handler shutdown must retain owner ledger for same-config retry, duplicate/uncertain work must never re-execute automatically, and no durable ledger or replay-enabling eviction is allowed.
- [X] T027 [US2] Route every Gemini functionCalls/cancellation entry and functionResponses ID through existing BackgroundToolManager in `src/reachy_mini_conversation_app/gemini_realtime.py` and shared completion handling in `src/reachy_mini_conversation_app/huggingface_realtime.py`; preserve enabled head, volume, status, dance/stop and sleep behavior, operational error dictionaries, app-local idle work, and needs_response=False nonblocking SILENT results.
- [X] T028 [US2] Adapt the existing camera result in `src/reachy_mini_conversation_app/gemini_realtime.py` to sanitized function metadata plus exactly one image/jpeg realtime input; enforce tool/global/--no-camera controls, omit b64_im from text/log/transcript, send no image on failure, and never recapture or stream continuously after send failure.
- [X] T029 [US2] Reuse `src/reachy_mini_conversation_app/prompts.py`, existing remember/forget operations and `src/reachy_mini_conversation_app/memory_routes.py` refresh callbacks; deliberately retire the owner state/handle and announce fresh Gemini context on injected-memory/configuration revision changes, without claiming provider pause/resume cannot update settings; preserve shared saved-memory IDs/retention/deletion, global injection versus tool-mutation controls and truthful error reporting.
- [X] T030 [US2] Carry explicit interrupted-fragment metadata through `src/reachy_mini_conversation_app/conversation_handler.py`, `src/reachy_mini_conversation_app/console.py`, and `src/reachy_mini_conversation_app/static/js/components/conversation-panel.js`; retain existing observer compatibility and transcript retention, and do not label abandoned assistant fragments as completed utterances; preserve the data-model "partial/completed/interrupted" state distinction.
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

- [X] T032 [P] [US3] Extend `tests/test_console.py` for rapid selection races, cancellation during backoff/setup/close, coalesced Retry, one active generation, stale callback rejection and truthful fresh/resumed status; replace the handler object while retaining owner state, inject the same tool call ID and prove no repeated action; fake a nonresponsive close to verify its five-second bound and usable switching/shutdown.
- [X] T033 [P] [US3] Extend `tests/test_gemini_realtime.py` for automatic GoAway recovery, valid/invalid/resumable=false handles, fresh fallback within remaining setup budget, handler replacement with retained ledger, model/voice/profile/toolset/memory invalidation, cancelled/late tool completion and unknown effects without replay; verify transient recovery versus authentication/access/configuration/hard-quota waiting.

### Implementation for User Story 3

- [X] T034 [US3] Serialize selection/configuration transitions in `src/reachy_mini_conversation_app/console.py`, using the existing restart lifecycle and sole scheduler; invalidate old generation before flushing/close, cancel obsolete backoff/in-flight attempts, keep the counter monotonic across fresh states, retain state reference only for same-provider/same-config recovery, and preserve other-provider settings/shared memories without live-history transfer.
- [X] T035 [US3] Enforce active owner/generation/epoch at receipt and before audio enqueue/send, observers, images and tool dispatch/results in `src/reachy_mini_conversation_app/huggingface_realtime.py`, `src/reachy_mini_conversation_app/gemini_realtime.py` and `src/reachy_mini_conversation_app/console.py`; never relabel delayed old events with a new epoch, buffer disconnected microphone input or let late cleanup regain ownership, and preserve existing cancellation behavior for already-started physical effects.
- [X] T036 [US3] Complete bounded transition cleanup in `src/reachy_mini_conversation_app/console.py` and shared handler lifecycle: use a monotonic 15-second combined setup budget, 5-second send limit and 5-second graceful close, invalidate ownership on timeout and abandon slow cleanup through public transport APIs without freezing configuration/switch/shutdown; retain exactly one common retry scheduler from T018 and one active media owner.
- [X] T037 [US3] Implement contextWindowCompression/sessionResumption updates and automatic serialized GoAway reconnect in `src/reachy_mini_conversation_app/gemini_realtime.py` using the same LocalStream-owned state through replacement handlers; handles stay "Memory only, never logged or exposed", latest resumable=false clears eligibility, changed configuration revision discards stale handles, and invalid resume visibly starts fresh within the original setup deadline before any new backoff.
- [X] T038 [US3] Reconcile the retained owner ledger in `src/reachy_mini_conversation_app/huggingface_realtime.py` and `src/reachy_mini_conversation_app/gemini_realtime.py` after valid resume: rebind only calls from that logical session, report uncertain effects without retry, resubmit a known result only for the same resumed call without re-execution, and report uncertainty before disposing a state that must start fresh; transfer no old queues or action requests.
- [X] T039 [US3] Display GoAway/reconnecting status, safe retry attempt/delay metadata, actionable permanent errors, fresh versus resumed context and uncertain-action feedback in `src/reachy_mini_conversation_app/static/js/views/settings.js` and `src/reachy_mini_conversation_app/static/js/components/conversation-panel.js`; permit manual Retry/provider selection throughout without displaying handles or claiming continuity falsely.
- [X] T040 [US3] Run US3 suites and switch/disconnection scenarios from `specs/001-gemini-backend/quickstart.md`, recording SC-005/SC-006/SC-007 results; use simulated time for at least ten automatic attempts on each provider capped at 30 seconds, validate permanent-error waiting and 15/5/5-second deadlines, cancellation during backoff/close, handler-replacement resumption, stale-handle invalidation and no replay of uncertain actions.

**Checkpoint**: All three stories can be demonstrated individually using the shared
foundation and earlier integrated increments; none requires unavailable later-story work.

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Complete documentation, cross-platform checks and end-to-end evidence.

- [X] T041 [P] Update the existing root `README.md` with Python 3.12 minimum setup, Gemini configuration, agreed voice order, indefinite same-provider retries capped at 30 seconds, operation deadlines/fresh-context boundaries, personal Developer API scope, on-demand camera/shared-memory disclosure and exclusions; reconcile the runtime change begun in T003 without adding a README or changing protected contribution files.
- [X] T042 [P] Document REACHY_MINI_CONVERSATION_BACKEND, GEMINI_API_KEY, GEMINI_MODEL, GEMINI_VOICE and precedence in `.env.example`; check the existing packaging mapping in `setup.py`/`MANIFEST.in` to ensure packaged defaults receive the same example, without introducing a redundant source file or committing a private .env.
- [X] T043 [P] Record the architecture-diagram update requirement for the future human-authored PR in `specs/001-gemini-backend/quickstart.md`, referencing `docs/scheme.mmd` and generated `docs/assets/conversation_app_arch.svg`; do not hand-edit SVG or create Markdown under docs/.
- [X] T044 Extend redaction/retention tests in `tests/test_gemini_realtime.py` and `tests/test_console.py` to prove failures/status/debug logging cannot expose keys, handles, raw image data or prior-provider live history; review shared-module changes for narrow logged exceptions, typed public signatures, and no new suppressions.
- [X] T045 Run a clean Python 3.12 locked install and the full Ruff/format/mypy/pytest gate plus `uv lock --check` against `pyproject.toml`, `uv.lock`, `src/` and `tests/`; record actual versions/results and supported-platform evidence in `specs/001-gemini-backend/quickstart.md`, require green checks and metadata/guidance alignment with constitution 2.0.0 before review, and leave unavailable platform evidence incomplete without CI edits.
- [ ] T046 Complete the 15-minute/10-exchange real-robot trial and remaining SC-001 through SC-011 evidence in `specs/001-gemini-backend/quickstart.md`: automatic resumed/fresh reconnects across service limits, 9/10 sub-second recognized interruptions with no abandoned speech, voice precedence, camera/memory failures and controls, and real device sample rates; retain fake-clock evidence for prolonged outages/deadlines separately rather than substituting it for hardware acceptance.
- [X] T047 Self-review the focused diff against `specs/001-gemini-backend/spec.md`, `specs/001-gemini-backend/plan.md`, and `AGENTS.md`, ensure no secrets or unrelated changes, and leave human review/PR creation to the developer using the existing `.github/pull_request_template.md` without modifying that template.

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
  continuity validation and stalled-operation cleanup, extending the common scheduler from
  US1 rather than adding a second recovery loop.
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

## Resume evidence (2026-10-29)

Additional T046 evidence (2026-10-30): the newly authorized trial was explicitly ended
through the page after 342.34 seconds including cleanup. Six spoken exchanges, three
recognized interruptions (1453/1532/1579 ms including observer reaction) and one
unrecognized attempt were recorded. No reconnect occurred. The app exited normally;
camera/memory remained off. T031/T046 remain unchecked and progress remains 45/47.
See quickstart.md for measurement limits and remaining acceptance.

Local implementation, simulated acceptance, the local gate and self-review are complete:
44/47 tasks are checked. T011/T012 cover actual-rate stereo PCM, acknowledgement gates, malformed
messages, missing credentials, safe errors, completed-exchange backoff reset and virtual
15/5-second budgets. T018/T036 now keep factory/revision failures inside recovery,
distinguish child-attempt cancellation from owner shutdown, capture old cleanup ownership,
and abort cancellation-resistant closes at five seconds. T021/T022 exercise multipart
interruption barriers, duplicate and simultaneous tools, late/cancelled results, unsupported
schemas, camera recovery and already-started effects. T032/T033/T040 cover ten switches,
rapid requests, waits/cancellation, stale observers, GoAway, handler-replacement deduplication,
all five configuration revisions and transient-versus-rejected resumption. T044 covers
normalized service errors, wire-log privacy, safe status and retired observer retention.
See quickstart.md for commands and limits of the simulated evidence.

T045 now passes locally on Windows/Python 3.12.12: the complete clean-environment suite
passes all 672 tests, including both MCP integrations, and repository-wide Ruff/format,
strict mypy and uv lock --check are green. The earlier tooling/test blockers were repaired
separately in fdd2066. The MCP fixture uses the documented pytest-asyncio loop-factory hook
with a portable Selector loop for its socket-only tests and native loops elsewhere; failed
server shutdown still raises after five seconds. This is a test-harness compatibility fix,
not a change or validation of the application's native Windows event-loop behavior.
The existing pytest-asyncio test dependency now declares >=1.4, matching the locked 1.4.0.
No test cases or lint rules were excluded. Linux/macOS and robot-platform evidence remain
unavailable and are not represented by this local gate result.

T047 self-review is complete: provider defaults/selection, ownership/deadlines, ledger and
privacy boundaries were checked against the feature documents and AGENTS.md. The feature
adds no new suppressions; contribution/CI/private environment files remain unchanged, and
PR creation remains with the developer. T020/T031/T046 retain the explicitly deferred live
service and physical-robot evidence. The subsequent live smoke trial confirmed speech,
physical nod and qualitative interruption; it did not measure the latency target or validate
camera/memory. No paid API call or PR is claimed. See quickstart.md for exact validation results.

The Windows shutdown correction now uses a public Selector loop factory only for the
LocalStream conversation loop on Windows, preserving other platforms and the global policy.
The isolated Gemini TLS probe reproduces WinError 10022 on Proactor and closes without
callback errors on Selector. A 30-second real-robot repeat shuts down with exit code 0 and no
callback error. The full gate passes 673 tests, strict mypy, Ruff/format and lock validation.
The user chose to finish only this correction this round; the extended trial and camera/memory
acceptance remain deferred, with T020/T031/T046 unchecked and the total still 44/47.

The subsequent user-authorized T020 trial recorded a greeting and four transcript pairs.
The user confirmed three audible exchanges and correct session-only phrase recall. An
unchanged-settings restart confirmed saved Gemini/Kore selection and reconnection, but the
user reported no reply in that short window. A requested repeat produced a greeting and
Chinese input/output transcripts, with 16000 Hz microphone input and nonzero speech peaks;
the user confirmed hearing its reply. All processes exited cleanly with camera/memory off.
T020 is checked using this live evidence plus the unchanged 673-test gate's simulated voice,
HF-default, setup-failure and recovery coverage. The earlier silent attempt's cause remains
unresolved; see quickstart.md. Progress is 45/47, with only T031/T046 unchecked and no
extended/camera/memory acceptance claimed.

T031 has partial live evidence: robot name and physical turns, post-fix dance/stop, rejected
camera/memory operations while disabled, continued Chinese conversation after failure, and
separate sleep/relaunch passed with user observations. The trial exposed daemon HTTP response
resets and lost connected microphone samples; both have failing-before/passing-after offline
regressions, and the corrected full gate passes 680 tests plus Ruff/format/mypy/lock checks.
The sample-count diagnostic improved from 77920/158080 to 157600/157760 forwarded samples.
Input buffering remains bounded and mute/connection boundaries discard old audio. See
quickstart.md for exact measurement limits and the outstanding isolated volume recheck.
T031/T046 remain unchecked because enabled-camera, cross-provider-memory and extended
acceptance are not covered by the authorized camera/memory-off trials; progress stays 45/47.

The isolated volume recheck now passes: one speaker change to 40 and one to 50, followed by
normal Chinese exchanges and verified microphone 100. An earlier timed-out write had applied,
so volume operations now allow a bounded confirmation interval and use one readback after
transport failure, never a write retry. Unverified outcomes retain explicit uncertainty in
Gemini's ledger. The full gate passes 685 tests plus Ruff/format/mypy/lock validation.
The subsequent T046 page was explicitly ended early: about 258 seconds, five spoken
exchanges, three observer-click upper bounds (1328/875/875 ms), no reconnect. These are partial
measurements, not a completed fifteen-minute/ten-interruption acceptance. T031/T046 remain
unchecked, camera/memory remain off, and progress remains 45/47; see quickstart.md.
