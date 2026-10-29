# Validation Guide: Optional Gemini Conversation Backend

This guide applies after implementation. Planning does not add Gemini support, dependencies,
RPC methods, or environment options. Follow the root README for environment/robot setup.

## Prerequisites

- Agreed issue and maintainer approach review; accepted usage/data budget.
- Python 3.12 minimum and Reachy with working microphone, speaker, and camera.
- Implementation aligns requires-python >=3.12, uv.lock, root README, and older Python
  minimum statements in repository guidance with constitution 2.0.0. Do not claim the
  current >=3.11 metadata already satisfies the new baseline.
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
