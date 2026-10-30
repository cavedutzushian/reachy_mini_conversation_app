# Validation Guide: Optional Gemini Conversation Backend

Follow the root README for environment/robot setup. The latest local result is **45/47
tasks complete, with the full local gate green**; earlier sections retain historical results.
Basic Gemini/robot voice acceptance passed; extended live-service and robot acceptance remains
deferred. The latest Windows shutdown fix and validation are recorded at the end of this file.

## Prerequisites

- Accepted service/account eligibility and usage/data budget before live trials. Local
  implementation and simulated tests are already authorized for personal customization;
  upstream Issue/maintainer review applies to a future contribution, not this local work.
- Python 3.12 minimum and Reachy with working microphone, speaker, and camera.
- Package metadata, lockfile, root README and repository guidance now target Python 3.12
  consistently with constitution 2.0.0. Verify the actual robot/platform environment too.
- Eligible personal Gemini Developer API account, Live model access, and quota.
- Private credentials in the existing process/instance environment configuration.
- Implementation dependencies installed and lock synchronized. Verify soxr wheels on actual
  Reachy hardware and supported desktops; availability is not proven by this plan.
- Disposable memory facts; no secrets or sensitive facts in validation material.

## Minimum-runtime environment after implementation

Once implementation has updated metadata and lock, validate a clean environment on the
minimum runtime, from the repository root:

```text
uv python install 3.12
uv sync --python 3.12 --locked
uv run python --version
```

Expected runtime is Python 3.12.x, with dependencies resolved from the committed lock.
Repeat installation/full checks on supported OS targets, recording unavailable environments
without claiming they passed. No environment or dependency changes occur during planning.

## Configuration after implementation

Add privately to the existing instance .env per the root README; never commit a real key:

```dotenv
REACHY_MINI_CONVERSATION_BACKEND=gemini
GEMINI_API_KEY=<your-private-key>
GEMINI_MODEL=gemini-3.8-live
GEMINI_VOICE=Kore
```

Saved UI selection overrides environment defaults. For untouched-default testing remove
the saved provider choice in a disposable instance; unsetting env does not override saved
selection. Keep BACKEND_PROVIDER and MODEL_NAME obsolete. See the
[selection contract](contracts/backend-selection.md) for precedence and readiness.

## Automated validation

From the repository root, with environment active, run separately and stop on first failure:

```text
ruff check . --fix
ruff format .
mypy --pretty --show-error-codes
pytest tests/ -v
uv lock --check
```

Do not hide unrelated failures with exclusions or weakened checks. Prior session checks
found Spec Kit script lint/format failures and pytest setup errors; their resolution is
not part of this planning claim. A green feature subset is not a green full gate.

After the new suites exist, targeted verification can use:

```text
pytest tests/test_gemini_realtime.py tests/test_console.py tests/test_settings_store.py tests/audio/test_resampling.py -v
```

Fake-wire coverage must prove setup acknowledgement, multipart content, both transcript
directions, PCM rate conversion, interruption boundaries, schema/name validation, silent
nonblocking responses, permissions/cancellation, duplicate IDs, rejected resume, old-generation
suppression, and redaction. HF regression tests must pass before and after shared extraction.

## Hardware trials

```text
reachy-mini-conversation-app --ui
```

1. Untouched instance defaults to HF with no Gemini key. Verify local/deployed modes and
   legacy startup personality/voice remain intact (SC-001).
2. Select Gemini, complete 15 minutes and at least ten exchanges with a chosen personality,
   and check greeting/transcripts. Automatic reconnect should handle service connection limits;
   record resumed/fresh indicators and backoff, not a single-socket guarantee (SC-002, SC-007, SC-008).
3. Interrupt ten responses. Measure recognition-to-stop time: at least nine within one
   second, no abandoned speech played later in any trial (SC-003).
   For this personal customization, the user waived interruption timing on 2026-10-30 and
   accepted that item as complete. The timed protocol above is retained for future optional
   measurement; it is not a remaining personal acceptance gate. Functional interruption
   and stale-output suppression still apply; endurance is not waived.
4. Request each essential action. Validate sleep separately because it ends the app;
   relaunch for remaining trials. Include an ordinary operational failure and subsequent
   successful spoken exchange. Inject exceptional failures in fake-wire tests (SC-004).
5. Perform ten switches including during speech/action execution. Confirm one active
   conversation, no duplicate motion, settings retained, and fresh live context (SC-005).
6. Request one observation of a distinct object. Confirm one snapshot and no continuous
   capture. Disable camera globally and via tool access separately; test unavailable camera
   and resumed conversation after failure (SC-009, SC-011).
7. Save a disposable fact with each provider, switch and recall, then forget and start fresh
   conversations on both providers. Verify fact deletion. Global memory off prevents
   injection/mutation but preserves stored facts. Disabling remember/forget alone does not
   disable saved-memory recall (SC-010, SC-011).
8. Force network loss and session closure for both providers. Confirm automatic same-provider
   recovery, correct resumed versus fresh status, and no replay of uncertain actions. Profile/voice/memory refresh
   must announce fresh context and prevent stale-handle resume (SC-007).
9. Cover missing/rejected key, unsupported model/voice, unavailable access, and quota errors.
   Use fake failures where real ones cannot be safely induced; do not manufacture quota
   exhaustion. Settings/Retry/manual HF remain usable and credentials stay private (SC-006).
10. Simulate prolonged recoverable outage for each provider with a fake clock and observe at
    least ten attempts capped at 30 seconds. Missing/invalid credentials, invalid configuration,
    denied access and hard billing/quota failures must wait for correction. Manual Retry
    expedites one attempt; provider change/shutdown cancels old attempts (SC-007).
11. Use fake transports to withhold setup acknowledgement, block a send, and ignore close.
    Verify 15/5/5-second deadlines, stale-ownership rejection and responsive configuration,
    provider selection and shutdown. Do not wait indefinitely or require real network faults.
12. Change Gemini voice sources in priority order: saved override, compatible personality,
    environment, Kore. An incompatible profile voice with no override requests correction;
    a saved valid override resolves it without rewriting the profile. HF resolution is unchanged.

## Evidence and limitations

Record OS, SDK/package version, model/voice, actual sample rates, timings, session transitions,
action outcomes, and sanitized failure reasons against SC-001 through SC-011. Mocks do not
establish hardware quality or account eligibility. Do not retain keys, handles, image payloads,
or personal transcripts in evidence. See [data model](data-model.md) and
[session contract](contracts/realtime-session.md) for precise ownership and continuity rules.

## Local implementation baseline (2026-10-28)

Personal-only local implementation and simulated tests authorized by the user. No paid
provider calls or physical robot verification are authorized in this run. Initial mypy:
53 source files pass. Initial Ruff: 55 existing Spec Kit script findings; format check:
seven existing Spec Kit scripts differ. Full pytest reached the local MCP integration
server and stalled; a repeated run reusing its temporary directory produced fixture errors.
A fresh temporary directory passes all 11 local VAD tests. Full-suite completion and
loopback integration investigation remain required; no green full gate is claimed.

Python 3.12 uv lock/sync succeeded, including soxr 1.1.0. Baseline excluding the two
local MCP integration tests: 588 passed; wheel-build test failed in sandbox with a cp950
subprocess decoding warning. Other operating systems and robot hardware remain unverified.

## First implementation progress and validation (2026-10-29)

Local personal customization now includes the optional Gemini wire adapter, persisted
provider/model/voice selection, HF default/factory preservation, settings controls and
Retry, shared logical state and send ownership, streaming PCM conversion, ordered
interruption barriers, background tools and duplicate-call protection, one-shot JPEG
submission, shared saved-memory refresh, and safe recovery/context feedback. This is
implementation progress, not completed acceptance or permission to make paid calls.

Windows environment: Python 3.12.12; reachy-mini 1.12.0; websockets 15.0.1; soxr 1.1.0;
jsonschema 4.26.0; NumPy 2.5.0; Ruff 0.15.20; mypy 2.2.0. websockets and soxr were flagged
during planning. jsonschema was separately flagged before declaring the already installed
transitive dependency directly for tool argument/schema validation. uv lock/sync on Python
3.12 and uv lock --check succeeded. A new isolated installation and non-Windows/robot
verification remain outstanding.

| Check | Observed result |
| --- | --- |
| Ruff check src tests | Pass |
| Ruff format --check src tests | Pass after formatting affected files; 107 files |
| mypy --pretty --show-error-codes | Pass, 55 source files |
| uv lock --check | Pass |
| Node syntax checks: settings.js, api.js, conversation-panel.js | Pass |
| git diff --check | Pass after removing the extra example-file trailing blank line |
| Final pytest excluding tests/test_mcp_client_integration.py | 629 passed in 21.56 seconds |
| Console regression after final uncertain-action feedback change | 81 passed in 10.55 seconds |
| Earlier complete pytest run in this resume | 609 passed in 27.28 seconds, before later test additions |
| Later complete pytest / isolated MCP integration | Interrupted after a stall; isolated first test reported PASSED, then no next result; cause unconfirmed |
| Repository-wide Ruff check . | Fail: 55 pre-existing findings under .specify scripts |
| Repository-wide Ruff format --check . | Fail: seven pre-existing .specify scripts |

Commands use .venv/Scripts/python.exe -m pytest with a fresh --basetemp under ignored
cache/ and -o cache_dir=cache/pytest-cache. The final broad command uses
--ignore tests/test_mcp_client_integration.py, so it is explicitly not a green full gate.
The existing MCP integration files, installed Spec Kit scripts, CI and contribution files
were not changed to bypass these failures. Source tests require no Gemini credentials,
paid calls or robot hardware. Shortened deadline constants exercise setup/send/close and
missing-interruption-barrier expiration; simulated retry waits cover ten failures on each
provider at 1/2/4/8/16/30/30/30/30/30 seconds. This does not replace the remaining race,
HF setup-acknowledgement, clean-install, full redaction or hardware acceptance cases in tasks.md.

Protocol implementation was checked against the [Live API wire reference](https://ai.google.dev/api/live)
and [Live tool guidance](https://ai.google.dev/gemini-api/docs/live-api/tools). These document
checks and mocks do not demonstrate model/account eligibility or real audio quality.

Architecture diagram follow-up: a future human-authored PR must flag that the provider
branch changes the diagram. Edit docs/scheme.mmd and regenerate
README.md's docs/assets/conversation_app_arch.svg through the normal diagram workflow;
the generated SVG has not been hand-edited. No Markdown was added under docs/.

Full review readiness remains blocked at T045. Keep paid API and physical robot checks
deferred under the user's personal-only authorization; do not check T046 or claim the
15-minute/ten-exchange, interruption latency, or physical action/camera acceptance passed.

## Lifecycle acceptance continuation (2026-10-29)

The remaining local simulation work is now complete through T044 (42/47 checked tasks).
This continuation supersedes the earlier list of missing lifecycle simulations, while
retaining all live-account, hardware and non-Windows limitations.

Fixes and regression evidence:

- HF now waits for session.updated before accepting microphone input, showing connected,
  starting tools or greeting. The same owner enforces the combined setup budget.
- Factory and configuration-revision failures are handled by recovery and leave status and
  provider selection available. A cancelled connection child no longer cancels the sole
  recovery owner during rapid selection.
- Virtual-clock tests exercise the real 15-second connect/setup budget, including ten seconds
  spent opening the socket and rejected-resume fallback inside the remaining five seconds.
  Both providers' actual five-second send limit retires ownership before transport abort.
- Cancellation-resistant Gemini close is bounded by a five-second wait plus transport abort.
  Late owner cleanup captures its original handler and cannot abort a replacement socket.
- Ten alternating provider switches and ten rapid restart requests preserve one media owner.
  Backoff tests cover ten attempts per provider and reset only after a completed exchange.
  Normal converter drain now finishes before marking the Gemini exchange completed.
- Actual 48 kHz float stereo capture becomes labelled mono PCM16 at 16 kHz, with no offline
  buffering. Required malformed messages and invalid acknowledgements fail safely.
- Multi-function calls preserve independent IDs; cancellation and late generations suppress
  results. A replacement handler reuses a completed camera result without executing or
  transmitting another image. Capture failure allows the next camera call to succeed.
- GoAway retains eligible context. Model, voice, profile, toolset and injected-memory revisions
  clear checkpoints. Transient handshake loss retains a valid handle; only identified resume
  rejection permits fresh fallback. Unknown close codes await correction/Retry.
- Raw remote HF errors no longer enter logs or assistant output. Debug-frame tests protect
  Gemini headers, handles and image data. Retired transcript/latency/VAD/interruption and
  completion callbacks cannot publish old content or reset current recovery state. Uncertain
  action notices are recorded once while call IDs remain deduplicated.

| Check | Result |
| --- | --- |
| Clean install | UV_PROJECT_ENVIRONMENT=cache/verify-python312; uv --cache-dir cache/uv sync --locked --python 3.12; pass, 127 installed packages |
| Minimum runtime/imports | Python 3.12.12; soxr, websockets and jsonschema imports passed |
| Source Ruff and format | Pass; 107 Python source/test files formatted |
| Strict mypy | Pass; 55 source files |
| Full clean-environment pytest | First MCP integration item passed, then fixture finalization stalled; interrupted after a 30-second diagnostic stack dump |
| Clean-environment pytest excluding only the two MCP integration items | 670 passed in 62.16 seconds |
| Lockfile | uv lock --check passed |
| Repository-wide Ruff | Still 55 pre-existing .specify script findings |
| Repository-wide formatting | Still seven pre-existing .specify script differences |

Complete run: cache/verify-python312/Scripts/python.exe -m pytest tests/ -v
--basetemp cache/pytest-clean-final -o cache_dir=cache/pytest-cache
-o faulthandler_timeout=30 (captured to cache/pytest-clean-final.txt).
The diagnostic stack is inside pytest_asyncio.plugin.finalizer and pytest_runtest_teardown,
with the Windows event loop waiting; an upstream/fixture root cause is not established.
The successful remainder run uses the same clean interpreter with -q and
--ignore tests/test_mcp_client_integration.py --basetemp cache/pytest-clean-remainder.
These ignored working artifacts and the exclusion are disclosed; no test configuration,
CI, MCP test fixture or Spec Kit script was changed to bypass the full gate.

Self-review found changes confined to the two provider/shared lifecycle modules, console,
related tests and these feature records. No dependencies, protected contribution/CI files,
private environment files, generated diagrams or transcript persistence were added in this
continuation. The earlier architecture-diagram follow-up still applies. Final review is
not claimed: T045 and T047 remain unchecked, alongside T020/T031/T046 for deferred live
service and physical robot trials.

## Full local gate and self-review completed (2026-10-29)

The previously blocked local gate is now green. Tooling/test repair commit fdd2066 is
separate from the Gemini runtime implementation. No runtime conversation modules changed
in this gate-repair continuation.

The 55 Spec Kit findings were fixed with concise API descriptions and import/format
corrections in the installed scripts. An AST comparison with the previous revision
confirmed executable statements unchanged after removing docstrings/import ordering from
the comparison. Six affected command entry points passed their --help smoke checks;
check_prerequisites.py still resolves the current feature. No lint exclusions or new
suppression comments were added.

A bounded teardown reproduction exposed WinError 10022 in Python 3.12 Windows Proactor
connection-lost callbacks, followed by a stranded server.wait_closed despite zero Uvicorn
connections/tasks. A complete HTTP readiness probe did not resolve it and was reverted.
The fix uses pytest-asyncio's documented loop-factory hook: the two socket-only local MCP
integration tests use the standard portable SelectorEventLoop, while other async tests use
asyncio.new_event_loop and the application keeps its native loop behavior. This is a test
harness compatibility choice; native Windows Proactor MCP server cleanup is not claimed
fixed. The fixture now raises on a five-second shutdown timeout and cancels leftover test
server work instead of hanging, without suppressing the failure.

The existing pytest-asyncio dependency minimum was flagged and set to >=1.4 to support
that public hook. uv.lock still resolves 1.4.0; no package version or runtime dependency
was added. See the [official loop-factory guide](https://pytest-asyncio.readthedocs.io/en/v1.4.0/how-to-guides/configure_loop_factories_per_test.html)
for the per-fixture selection pattern. The original discovery, authentication, invocation
and timeout assertions still execute against a real loopback HTTP MCP server.

| Check | Latest result |
| --- | --- |
| Locked environments | uv sync --locked --python 3.12 passed for the project and clean cache/verify-python312 environment |
| Full clean-environment tests | 672 passed in 50.06 seconds; no ignored or skipped MCP tests |
| Repository-wide Ruff check . | Pass |
| Repository-wide Ruff format --check . | Pass; 119 files formatted |
| Strict mypy | Pass; 55 source files |
| uv lock --check | Pass; 131 resolved packages |
| git diff --check | Pass |
| Spec Kit CLI smoke checks | Six --help entry points passed |

Full test command: cache/verify-python312/Scripts/python.exe -m pytest tests/ -q
--basetemp cache/pytest-full-gate-fixed2 -o cache_dir=cache/pytest-cache. The clean interpreter
is Python 3.12.12 on Windows. No other operating system or robot deployment was tested.

T047 self-review checked FR-001 through FR-017 against provider selection/defaults, shared
session ownership, setup/send/close limits, retry classification, deduplication, snapshots,
shared-memory controls and transcript/privacy boundaries. The automated evidence supports
local implementation and simulated behavior; account access, speech quality, actual device
sample rates, physical actions, camera observations and timing targets remain unverified.
A diff check against pre-implementation revision 2fdd366 confirmed protected contribution/CI
files and private .env files unchanged, and no new source suppressions/future-annotations
imports. The existing README/environment guidance and architecture-diagram follow-up remain
applicable. The developer retains human review and any future PR creation.

T045 and T047 are checked for this completed local scope. T020, T031 and T046 remain
unchecked for the explicitly deferred live-service and hardware acceptance. No paid API or
real robot calls were made, and no PR was opened.

## Live acceptance started (2026-10-29)

The user confirmed a free-tier Gemini key and authorized spoken conversation and basic
robot actions while present. The budget remains zero paid usage. Camera and long-term
memory remain disabled for this trial; camera/memory acceptance is still outstanding.

- Read-only daemon discovery found `http://127.0.0.1:8000`: state `running`, version
  `1.13.0`, simulation disabled, and robot app lock free before launch.
- A single bounded Gemini Live setup-only probe returned `setupComplete`; it sent no
  microphone audio, images, tools, memory or greeting. Account access is confirmed for
  the configured model, without asserting unlimited free quota.
- A four-minute application trial uses a disposable ignored instance under
  `cache/live-gemini-acceptance`, Gemini selection, Kore voice, default personality,
  camera hard-off and memory disabled. Existing user settings are unchanged.
- The running application produced an assistant greeting, an input transcript and a
  Chinese assistant reply. A spoken nod request invoked `dance` with `simple_nod`
  and repeat `1`. The user confirmed audible speech, physical nod and successful
  interruption with no observed abnormality. Logs also show playback-queue flushing
  and a subsequent assistant reply. This confirms the basic smoke trial; interruption
  latency was not measured and the ten-attempt target was not exercised.
- Environment limitations: client SDK `1.12.0` differs from daemon `1.13.0`; seven
  audio DSP parameter writes were denied. Audio pipelines and conversation nevertheless
  started. These warnings are not resolved by this trial.
- At the four-minute deadline the stop event ran, audio queues were cleared, movement
  management and head wobbling stopped, and the process logged `Shutdown complete`
  with exit code `0`. Windows asyncio also logged `WinError 10022` in the Proactor
  connection-loss callback during teardown. Shutdown is therefore not error-free;
  investigate this runtime/platform cleanup issue before claiming clean live acceptance.

T020, T031 and T046 remain unchecked: this partial evidence does not establish all
required spoken exchanges and settings checks, interruption timing, reconnect behavior,
camera/memory behavior or the fifteen-minute acceptance target. No PR was opened.

## Windows shutdown correction (2026-10-29)

A setup-only Gemini WebSocket probe using Python 3.12.12's native Windows Proactor loop
reproduced the same `WinError 10022` from `_call_connection_lost` during TLS cleanup, without
the robot SDK, microphone, camera, tools or generated speech. The corresponding Selector
probe received `setupComplete` and reported no callback errors. This isolates the observed
failure from robot action/media shutdown; it does not establish that every Windows cleanup
failure has the same cause. An ordinary local WebSocket echo closed cleanly on both loops.

LocalStream now passes a Windows-only `asyncio.SelectorEventLoop` factory to `asyncio.run`.
Other platforms retain their default loop, and the process-wide event-loop policy is unchanged.
No SDK/Python internals are patched, errors remain visible, and no dependency changes were
needed. Existing application tools do not use asyncio subprocess/pipe APIs. Custom tools on
this Windows conversation loop must use blocking subprocess APIs through `asyncio.to_thread`
instead; see the [Python platform limitations](https://docs.python.org/3.12/library/asyncio-platforms.html).
The root README documents this trade-off.

A new offline console regression exercises real loopback socket closure, checks callback
errors and preserves the global loop policy. It also passed before the correction: the local
plain-socket test alone does not reproduce the remote TLS failure. The isolated live TLS
comparison above supplies the failing/passing evidence for that failure.

| Check | Result after correction |
| --- | --- |
| Console suite | 99 passed |
| Full Python 3.12.12 suite | 673 passed in 23.03 seconds |
| Ruff check . --fix / format . | Pass; 119 files unchanged by formatting |
| Strict mypy | Pass; 55 source files |
| uv lock --check / git diff --check | Pass; dependency lock unchanged |
| Bounded robot startup/shutdown | 30-second deadline, exit code 0, Shutdown complete |
| Callback errors in robot repeat | No WinError 10022 or asyncio callback error logged |

Full test command: `cache/verify-python312/Scripts/python.exe -m pytest tests/ -q
--basetemp cache/pytest-win-close-gate -o cache_dir=cache/pytest-cache`. The ignored local
repeat log is `cache/live-gemini-cleanup-fixed.log`; no credentials or live transcripts are
added to tracked files. The repeat reached Gemini tool-manager startup and a welcome-emotion
call; it does not add a verified spoken exchange. SDK 1.12.0 versus daemon 1.13.0 and the seven
denied audio parameter writes remain separate environment limitations.

The user explicitly limited this run to the shutdown correction and kept camera/memory off.
T020, T031 and T046 therefore remain unchecked (44/47 complete). The fifteen-minute trial,
measured ten-interruption target, full selection/reconnect matrix, camera/memory acceptance,
and unavailable platform evidence remain outstanding. No PR was opened.

## T020 spoken trial and persistence check (2026-10-29)

The user authorized a roughly five-minute three-exchange trial and restart, with camera and
long-term memory still disabled and zero paid usage. Both processes read the existing
disposable instance settings; neither rewrote provider/voice settings before loading them.

- First process: the saved selection was Gemini with Kore. Logs recorded one spoken
  greeting and four user/assistant transcript pairs. One short input was recognized as
  English instead of the expected test question, so the user was invited to repeat it.
  The user confirmed all three requested exchanges had audible replies and the disposable
  session-only phrase was recalled correctly. No long-term memory was enabled or written.
- Restart: the same saved Gemini/Kore selection loaded and the Gemini tool manager started.
  A welcome-emotion call was recorded, but no spoken greeting or user/assistant transcript
  pair was captured during the bounded 75-second restart window. Persisted configuration
  and reconnection were confirmed, but the user reported no reply to their question.
  This unsuccessful window is retained as evidence, not counted as a spoken success.
- Both processes logged `Shutdown complete`, returned exit code 0 and retained runtime
  Gemini/Kore with camera/memory false. Neither log contained a backend-attempt failure
  or `WinError 10022` callback error. The previously documented SDK-version/audio-parameter
  warnings remain unresolved.

Only ignored local harness/log files were created under `cache/`. The first PowerShell
redirect rendered Chinese text incorrectly; the restart harness writes console records
directly with a UTF-8 FileHandler for subsequent inspections. This is a diagnostic capture
limitation, not evidence that the application corrupted provider transcripts. No personal
transcripts or credentials are copied into tracked evidence.

The user requested a repeat of the post-restart check. A new process loaded the same saved
Gemini/Kore settings and allowed up to five minutes. An ignored diagnostic subclass called
the unchanged Gemini receive method and recorded only frame counts, amplitude peaks and
sample rate; it neither patched SDK internals nor saved raw audio. The input was 16000 Hz.
Initially quiet input rose to peaks around 0.64 and 0.74 while the user spoke. The provider
produced a matching Chinese input transcript and assistant reply, and the user confirmed
hearing the reply. An opening spoken greeting was also recorded. This repeat confirms a
successful post-restart exchange, but does not establish why the earlier attempt was silent.

The repeat was explicitly stopped after confirmation, logged `Shutdown complete` and exited
with code 0, without a backend failure or callback error. Camera/memory remained false and
Gemini/Kore remained selected. Existing SDK-version and audio-parameter warnings persist.

T020 is now checked: live three-exchange/personality/greeting/transcript evidence, saved
selection and restart evidence are combined with the existing passing offline coverage for
voice precedence/isolation, HF defaults without Gemini credentials, bounded setup failure,
permanent-error waiting and automatic recovery for both providers. These error/quota cases
were simulated, not deliberately triggered on the account. The unchanged application's
673-test full gate remains the latest automated result; no dependency changes were made.
T031/T046 remain pending their separate tool/camera/memory/extended trials. Progress is
45/47; camera/memory were not enabled, and no PR was opened.

## T031 partial robot acceptance and input corrections (2026-10-29)

The user authorized the basic tool trial while keeping camera and persistent memory off.
Two reproducible defects were corrected; no SDK internals, dependencies, lockfile or protected
contribution/CI files changed.

**Daemon responses:** robot_status failed with WinError 10054 before correction. Read-only
comparisons found intermittent resets with immediate-close requests, including an HTTPX
request explicitly using `Connection: close`. The offline close-sensitive server regression
failed before the correction. The app now reuses its existing HTTPX dependency to read the
response before closing, connects directly to the SDK-selected daemon without environment
proxies, and does not retry requests. Status/detail handling, malformed/truncated bodies and
uncertain POST/no-retry behavior remain tested. Three actual daemon reads and the subsequent
spoken robot-name query succeeded. See Python's documented
[urllib Connection: close behavior](https://docs.python.org/3.12/library/urllib.request.html)
and [HTTPX client cleanup](https://www.python-httpx.org/advanced/clients/).

**Microphone continuity:** the SDK supplied stereo chunks of 160 samples at 16000 Hz. A
ten-second diagnostic with a five-millisecond receive delay exposed overwritten pending
audio. The deterministic offline sample-order regression also failed before correction.

| Diagnostic | Captured samples | Forwarded samples |
| --- | ---: | ---: |
| Before coalescing | 158080 | 77920 |
| After coalescing | 157760 | 157600 |

These are local diagnostic measurements, not provider latency or speech-recognition scores.
The remaining 160 samples in the second run were at its stop boundary. Pending same-connection
chunks are now coalesced, with a 250 ms limit and an overflow warning rather than silently
overwriting every prior chunk. Generation checks and a microphone epoch discard pending audio
across connection replacement or mute/unmute. Warmup discard, exact sample order and rapid
mute/unmute privacy are covered without API calls. The user subsequently confirmed that the
spoken stop instruction correctly stopped the dance; earlier attempts had been misrecognized.

| Live observation | Result |
| --- | --- |
| Robot name, left/front head movement | Tool success; user confirmed physical turns |
| Volume | Calls completed; following speech degraded in the earlier trial; isolated post-correction volume-change acceptance still needed |
| Dance/stop after continuity correction | User confirmed correct stopping; stop_dance completed |
| Disabled camera | Tool returned failure before capture; user heard inability feedback |
| Disabled memory | Two failed remember calls; no memory.v1.json created; user heard inability feedback |
| Conversation after tool failures | User confirmed normal Chinese replies |
| Sleep, then independent relaunch | User confirmed sleep/stop, wake-up and Chinese reply; both processes exited 0 |

The test instance now uses the existing Chinese (`zh`) language setting. At the user's
request, microphone volume was restored to 100; speaker volume remained 50. Increasing input
gain alone had not resolved stop recognition. Some earlier and later inputs were still
misrecognized, so perfect ASR or a sole cause for every recognition failure is not claimed.
SDK 1.12.0/daemon 1.13.0 and seven denied audio DSP parameter writes remain limitations.

Latest gate: **680 tests passed in 22.30 seconds**, strict mypy passed for 55 source files,
repository-wide Ruff/format passed (119 files), uv lock --check and git diff --check passed.
Full test command: `cache/verify-python312/Scripts/python.exe -m pytest tests/ -q
--basetemp cache/pytest-t031-audio-gate -o cache_dir=cache/pytest-cache`. Only Windows/Python
3.12.12 was exercised. All robot test processes have stopped; camera/memory remain off.
Temporary T031 transcript logs are removed after recording this sanitized summary; no raw
audio was saved. Product transcript retention is unchanged.

Progress remains **45/47**. T031 stays unchecked for enabled-camera observation/failure,
cross-provider memory and remaining independent acceptance; T046 stays unchecked for the
fifteen-minute, measured-interruption, switch/reconnect and full acceptance matrix. Repeated
short sessions do not substitute for that endurance trial. No PR was opened.

## Volume completion verification and partial T046 run (2026-10-29)

The independent speaker trial initially confirmed normal conversation after setting 40,
but restoration responses timed out. Readback showed 60 had actually applied; the spoken
restoration had been transcribed as 60. A single explicit restoration returned the speaker
to 50, with microphone 100 unchanged. This is evidence that a lost response cannot safely
be treated as a write that did not happen.

Volume writes now use a ten-second network timeout for the daemon's confirmation sound.
After a transport/unreadable-response failure, the tool reads the level once without
repeating the POST. A matching level confirms the desired state. If it cannot be verified,
the tool reports a fixed, safe uncertainty message instructing the model to ask the user
before another attempt. Known HTTP rejections remain failures. Gemini preserves this
specific uncertainty in its ledger/feedback rather than replacing it with a generic error;
replayed call IDs cannot dispatch the action again. No dependency or SDK changes were made.

The corrected real trial produced exactly one successful speaker write to 40 and one to
50. The user confirmed both settings and normal subsequent Chinese conversation, with
no uncertainty/retry prompt. The final readback was speaker 50 and microphone 100. The
earlier transient SDK heartbeat loss during confirmation sounds remains an environment
limitation; extending the tool timeout does not fix the daemon's event-loop behavior.

Latest full gate: **685 passed in 44.84 seconds**, strict mypy passed for 55 source files,
repository-wide Ruff/format passed (119 files), uv lock --check and git diff --check passed.
Command: `cache/verify-python312/Scripts/python.exe -m pytest tests/ -q --basetemp
cache/pytest-volume-readback-gate -o cache_dir=cache/pytest-cache`. Failing-before/passing-after
tests cover applied-but-timed-out writes, failed/mismatched readback, explicit HTTP rejection,
and preserved uncertainty with no same-ID replay. Live uncertainty failures were not induced.

The user then authorized a fifteen-minute, camera/memory-off trial using the ignored local
measurement page in `cache/t046_acceptance.py`. The timer began with connected microphone
input. For each armed trial, it measured receipt of the server's interrupted marker until
the user's click after hearing the old speech stop. This includes observer reaction and
loopback-request time, so it is an upper bound on that client-marker-to-audible-stop interval,
not a measurement from speech onset or proof that a longer bound means slow robot playback.

The page received its explicit early-end command. The process shut down normally, exit 0;
the summary elapsed time was 258.27 seconds including final cleanup. It recorded five
completed spoken exchanges and three measured interruptions: **1328, 875, 875 ms**; two
upper bounds were sub-second. One initial connection, no GoAway/reconnect and 16000 Hz
device input/output were observed. These data do not establish fifteen minutes, ten exchanges,
9/10 sub-second interruptions, or resumption behavior. The sanitized numeric summary is
`cache/t046-acceptance-summary.json`; transcript text was filtered out of the trial log.
Temporary trial logs were removed after recording this evidence, and no raw audio was saved.

The isolated volume recheck is complete. Overall progress remains **45/47**: T031 still
requires enabled-camera/cross-provider-memory and remaining independent acceptance; T046
still requires its full endurance/interruption and switch/reconnect matrix. Camera/memory
remain disabled, all trial processes are stopped, and no PR was opened.

## Second partial T046 trial (2026-10-30)

The user authorized a new fifteen-minute trial with camera and memory disabled, then
confirmed the local page and opening greeting worked. The page subsequently received its
explicit early-end command. Shutdown completed normally with exit 0 after 342.34 seconds
including cleanup; no automatic restart was attempted.

The trial recorded six completed spoken exchanges, three recognized interruption timings
of 1453, 1532 and 1579 ms, and one unrecognized attempt. These timings include observer
reaction and loopback request time, using the same server-marker-to-observer-click method
described above; they do not isolate audible playback-stop latency. None of the three
upper bounds was below one second. One connection, no GoAway/reconnect, and 16000 Hz
device input/output were observed. No transcript text or raw audio was retained in the
sanitized summary. This partial run does not establish fifteen-minute endurance, ten
exchanges, 9/10 sub-second interruptions, or session resumption.

Progress remains 45/47, with T031 and T046 unchecked. No source or dependency changes
were made, so the previously recorded 685-test gate was not rerun for this evidence-only
update. Camera and memory stayed disabled; the test app and local measurement server
have stopped. No PR was opened.

## Single-photo T031 trial (2026-10-30)

The user explicitly authorized one test-object snapshot only upon a spoken request,
with long-term memory off. An ignored application-level diagnostic harness temporarily
enabled camera access in the disposable instance and delegated the first camera call
and image send to the existing implementation. It limited this trial to one camera call
and one image transmission; no SDK code was modified. The user was instructed to request
an object/color description without stating the answer, followed by a Chinese greeting.

Observed counts: one admitted camera call, one successful JPEG result, and one image
message sent. One additional camera call was blocked by the diagnostic limit, so this
run does not prove the unrestricted model would request only one snapshot. No image
payload or transcript text was retained in the trial log. The user subsequently confirmed
that the robot could read the photo and describe it correctly. The actual object/color
was not supplied, and the subsequent spoken greeting remains unconfirmed. SC-009 is
not fully passed: no capture failure was injected. No memory operations were enabled.

The test exited normally with code 0. The disposable instance was verified restored to
camera_enabled=false and memory_enabled=false. Sanitized counts are retained locally in
cache/t031-camera-summary.json; the temporary runtime log was removed. No product source
or dependency changes were made. T031 and T046 remain unchecked, with progress 45/47.

## Camera-failure recovery trial (2026-10-30)

The user authorized a short voice test with no real capture or image transmission and
memory off. The ignored diagnostic harness replaced only the application camera tool
instance with a subclass delegating to the original Camera implementation using a fake
media dependency that returned no frame. Its test-only dependency had camera permission
enabled to reach the no-frame branch; the real instance stayed camera-disabled and used
the no-camera flag. SDK internals and product source were unchanged. Image sends were
prohibited by the diagnostic handler.

One fake frame request and one failed camera result were observed, followed by three
completed spoken exchanges (including the failure response). The real frame API was not
called and no image message was sent. The user confirmed the first response correctly
reported inability to obtain an image. The first follow-up was recognized as another
language; a repeated request then received a correct Chinese reply. This demonstrates
continued conversation after the injected tool failure, while retaining the first
follow-up language-recognition failure rather than claiming uninterrupted Chinese
recognition. It does not exercise a real camera hardware failure.

The process exited normally with code 0. Camera and memory settings were verified false;
the sanitized summary is cache/t031-camera-failure-summary.json. The temporary log contained
no transcript/image payload and was removed. This evidence-only update passed git diff
--check; the previous 685-test product gate was not rerun. T031 and T046 remain unchecked
at 45/47, pending remaining memory, interruption, endurance and switch/reconnect acceptance.

## Cross-provider memory trial (2026-10-30)

The user authorized one nonsensitive fact in a separate disposable instance, with camera
off, deletion afterward and memory disabled at completion. The ignored harness used
cache/t031-memory-acceptance, initially empty, and the existing provider handlers, tools
and memory APIs. Six sequential app launches used explicit saved provider selection;
these are fresh-session memory tests, not runtime-switch race acceptance. No SDK or
product source was changed. Offline preflight confirmed the language was zh and the
Chinese reply instruction was present; this does not guarantee correct ASR.

- Hugging Face saved the designated test-badge fact successfully (one stored fact); the
  user heard a normal Chinese response. In a fresh Gemini session, the user confirmed
  the correct badge answer without supplying it. Gemini's forget tool then succeeded,
  leaving zero facts. A later write was explicitly requested by the user, not a replay;
  that additional content was cleared through the existing API in this isolated store.
- A fresh Gemini session saved the same designated fact successfully, although the user
  reported its spoken reply was unrelated to memory. A fresh Hugging Face session then
  correctly recalled the badge, as confirmed by the user.
- Hugging Face initially gave a normal spoken reply to a forget request without an
  observed delete result. A more explicit request invoked forget but failed: its simplified
  Chinese query did not match the stored traditional Chinese phrase. The existing
  case-insensitive substring matching does not convert Chinese scripts. The user later
  reported inability feedback after the suggested common-script keyword retry; no
  successful Hugging Face forget call was observed. Do not count this as tool deletion.
- The test store was cleared using the existing API, then each provider was launched
  fresh with zero facts. The user reported no relevant badge information from Hugging
  Face (not an explicit confirmation of an unknown-answer response), and Gemini explicitly
  reported having no information. These results follow API cleanup, not successful
  Hugging Face tool deletion.

The process exited normally with code 0. Final verification found zero stored facts and
camera_enabled=false / memory_enabled=false. No transcript text or fact text was retained
in the sanitized count summary at cache/t031-memory-summary.json. The temporary runtime
log was removed; no images or raw audio were saved. Other instances were not changed.
This documentation-only update passed git diff --check; the existing 685-test gate was
not rerun. SC-010 remains incomplete because successful tool deletion and its fresh-session
absence checks in both directions were not established. T031/T046 remain unchecked at
45/47; remaining language, interruption, endurance and runtime switch/reconnect results
must not be inferred from these memory trials.

## Exact-ID memory deletion remediation (2026-10-30)

The live query mismatch exposed that the model could only request text-based deletion,
although the existing memory API already accepted fact IDs. Saved-memory instructions
now include each fact's existing ID and tell the model to copy it into forget. The tool
accepts memory_id without query, prefers an explicitly supplied ID, and reports an unknown
ID without falling back to a query that could remove another fact. Query-only calls keep
their existing substring behavior. No script conversion, new dependency, storage format,
SDK change or provider-default change was introduced. Root README documents the behavior.

Regression tests failed before implementation (four failures, five passes), covering
missing prompt IDs and ignored IDs. After the fix, 54 related tests passed; the complete
suite passed with 690 tests in 37.16 seconds. Strict mypy passed for 55 source files,
Ruff/format passed for 119 files, uv lock --check resolved 131 packages and git diff --check
passed. A subsequent test-only assertion checked the tool schema accepts ID-only arguments;
the nine memory tests and repository lint/format passed again. Tests also cover translated
queries, preservation of other facts, unknown IDs without query fallback and memory-off
protection. All checks used Windows/Python 3.12; no live API or robot trial was started.

The remediation enables exact deletion but does not prove either model will choose the
correct ID in live speech. The previous HF deletion failure remains recorded, and fresh
cross-provider deletion/absence acceptance must be repeated before SC-010 passes. Camera
and memory remain disabled in the test instances. T031/T046 remain unchecked at 45/47.

## Exact-ID deletion live revalidation (2026-10-30)

The user continued implementation and completed the previously authorized isolated,
single-fact memory trial after the ID-based deletion fix. The same diagnostic harness
delegated to the product tools and additionally recorded only whether a forget invocation
supplied memory_id; it did not supply IDs or change tool arguments. Camera stayed hard-off.
Seven sequential app launches created fresh conversations with explicit provider selection;
these launches do not count toward runtime-switch or reconnection acceptance.

1. Hugging Face stored the designated fact successfully, producing one fact and a normal
   Chinese reply. Gemini then correctly recalled it without the user supplying the answer.
   Gemini's forget call supplied memory_id and succeeded, leaving zero facts; the user
   confirmed the expected response. Fresh Hugging Face and Gemini conversations both
   reported no badge information, as confirmed by the user.
2. The user then asked Gemini to store the same designated fact. Its remember call succeeded,
   producing one fact. A fresh Hugging Face conversation correctly recalled it without an
   answer hint. Its forget call supplied memory_id and succeeded, leaving zero facts; the
   user confirmed the reply. Fresh Hugging Face and Gemini conversations both explicitly
   reported having no badge information.

This completes the real-account save/recall/tool-delete/fresh-session-absence sequence in
both directions and confirms that both models used the ID deletion path. Earlier failed
trials remain historical evidence; no manual API cleanup was used between these successful
delete and absence checks. This run does not establish general ASR accuracy or every
memory-failure scenario.

Final defensive cleanup found zero facts. The process exited normally with code 0, and
settings were verified camera_enabled=false and memory_enabled=false. Only metadata was
retained at cache/t031-memory-summary.json; the temporary runtime log was removed, and no
image or raw audio was saved. This evidence-only update passed git diff --check; no product
code changed, so the previous 690-test gate was not rerun. Progress remains 45/47 because
T031/T046 still require the interruption timing/endurance and remaining acceptance matrix.

## Runtime provider switching and movement cleanup (2026-10-30)

The user authorized ten runtime provider switches, including speech and nod-dance cases,
with camera and memory off. An ignored loopback-only diagnostic page sent backend.config
through the product's existing /rpc WebSocket; it did not replace the provider-selection
logic. The initial page had a JavaScript newline-escaping error introduced in the harness.
An offline node --check reproduced the syntax failure; corrected escaping passed that
check before the page was restarted. No switches from that page failure were counted.

The first working run scored four quiet/speech switches as normal, then marked the fifth,
HF-to-Gemini during queued nod dance, abnormal. The user confirmed movement continued
after switching. The agent halted the trial through its end endpoint; any unscored further
connection was not counted as acceptance. The sanitized pre-fix summary is retained locally
at cache/t046-switch-before-fix-summary.json.

Dance submits completed work to the shared movement queue, so shutting down the old tool
manager did not remove already-queued motion. LocalStream now checks whether the provider
changes before discarding old logical state and posts the existing clear_move_queue command
after invalidation, before yielding to handler shutdown/replacement. The movement worker
applies that command on its normal tick, stopping active and queued primary moves. This
does not claim instantaneous physical stopping or cancellation of every external action.
Same-provider automatic recovery does not enter this new branch. No SDK patch, new
dependency or provider-default change was made; root README was updated.

The ten-switch ownership regression failed before the fix and passed afterward. It now
checks that each replacement starts after the movement-clear request and rapid repeated
selection of the same target does not repeatedly clear movements. Full gate: 690 tests
passed in 36.35 seconds, strict mypy passed for 55 source files, Ruff/format passed for
119 files, uv lock --check resolved 131 packages, and git diff --check passed.

The corrected live run recorded ten explicit backend.config switches, five in each
direction: six quiet, two during speech and two during nod dance. All ten were marked
normal by the user after a Chinese follow-up and checks for old speech/motion continuing
or repeating. Both motion-switch directions passed. Eleven connected generations were
observed, with monotonically increasing generation values. The first sampled context for
one HF connection was unavailable; the other recorded contexts were new. These samples
do not establish context resumption or absence of every possible stale-history path.

The page's end command stopped the completed trial, exit 0. The final test settings were
HF, Gemini voice Kore, language zh, camera=false and memory=false. Transcript text was
filtered out and the temporary runtime log was removed; the numeric/observer summary is
cache/t046-switch-summary.json. No raw audio or images were saved. This establishes the
observed ten-switch behavior, not fifteen-minute endurance, measured interruption latency
or automatic outage recovery. T031/T046 remain unchecked at 45/47 for the remaining matrix.

## Same-provider reconnect acceptance (2026-10-30)

The user authorized closing only the test app's own cloud connections, with camera and
memory off; neither the computer network nor robot daemon was disabled. The ignored
diagnostic harness delegated to product handlers and called their connection's public
close method. No Retry or provider-switch command was used to recover from each closure.
The standard handle-based protocol was cross-checked against Google's
[Live API session management reference](https://ai.google.dev/gemini-api/docs/live-api/session-management).

- Gemini with a valid checkpoint: the user supplied a session-only nonce and heard the
  requested acknowledgement. A local close was classified connection_lost; an automatic
  same-provider connection appeared about 2.33 seconds later, generation 1 to 3, context
  resumed. The first recall attempt did not retrieve the nonce. On a repeated question,
  the user confirmed the correct nonce and explicitly accepted this item as complete.
  Preserve the first miss; the run does not establish first-attempt recognition accuracy.
- Hugging Face: local close was followed automatically by another HF connection about
  3.24 seconds later, generation 1 to 3. Its earliest diagnostic context sample was
  unavailable; subsequent live state was new. The user confirmed normal Chinese speech
  after recovery. No HF context-resumption claim is made.
- Gemini without a checkpoint: in a new Gemini test stage, the user first confirmed a
  different session-only nonce could be recalled. The harness deliberately cleared the
  app-owned resumption handle/eligibility and closed that connection. Automatic recovery
  appeared about 1.65 seconds later, generation 1 to 4, context new. The user confirmed
  the new conversation had no previous nonce information. This simulates an unavailable
  local checkpoint, not a server rejection of a supplied handle.

Each stage used the same provider for recovery; the HF-to-Gemini stage transition was a
separate app launch and is not counted as a reconnect. These short idle-connection trials
do not prove service GoAway behavior, a prolonged network outage, deadlines under load,
pending-action reconciliation or fifteen-minute endurance. No source/dependency change
was needed. The earlier unsuccessful first nonce response remains part of the evidence.

Both test processes exited normally with code 0. Final settings were camera=false and
memory=false; no memory file was created. Sanitized metadata is retained locally in
cache/t046-gemini-resume-summary.json, cache/t046-hf-reconnect-summary.json and
cache/t046-reconnect-summary.json. Handles, transcript text, raw audio and images were
not retained in these summaries; the temporary runtime log was removed. This evidence-only
update passed git diff --check; the previous 690-test gate was not rerun. T031/T046 remain
unchecked at 45/47, including the full endurance/measured-interruption and remaining matrix.

## User-accepted interruption-timing waiver (2026-10-30)

The user explicitly instructed: “略過插話計時並視為完成” (skip interruption timing and
treat it as complete). The quantitative SC-003 timing item is therefore closed by user
waiver for personal acceptance. No new timing test ran, and no 9/10 sub-second result is
claimed. Earlier partial timings, failed/unconfirmed observations and measurement limits
remain unchanged. Functional barge-in/stale-output regressions and recorded live behavior
remain the evidence for interruption functionality.

T031 is now closed for personal acceptance using that waiver together with the recorded
essential-tool, sleep/relaunch, camera, failure-recovery, permission and bidirectional
memory evidence. T046 remains open: the complete fifteen-minute/ten-exchange endurance
trial and remaining acceptance matrix have not been waived. Previous short local-close
trials do not become service-limit or prolonged-network-outage evidence by this decision.
Spec, plan and task wording now distinguish waived measurement from observed success.

Progress is 46/47. No product code, dependency or runtime setting changed; no test app was
started. Camera and memory remain off. This documentation-only update passed git diff
--check and retains the previous 690-test gate without rerunning it.
