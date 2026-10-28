# Research: Optional Gemini Conversation Backend

**Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

Research combined repository inspection with a delegated read-only review of primary Google
documentation. No live account, robot, latency, pricing, or deployment validation occurred.
Availability must be rechecked during implementation; examples are not service guarantees.

## Transport and dependencies

- **Decision**: Use a typed direct Gemini Live WebSocket adapter. Declare the already locked
  websockets dependency directly and add soxr for streaming playback conversion; flagged
  before implementation, neither dependency nor lock changed during planning.
- **Rationale**: HF already imports websockets (locked at 15.0.1). Direct JSON is documented.
  The SDK player consumes samples at its device rate, so rate labels alone cannot convert
  Gemini's 24 kHz output; mismatched samples change pitch and duration.
- **Alternatives considered**: google-genai supplies generated types but introduces an SDK
  dependency/lifecycle. Stateless per-chunk interpolation loses streaming filter continuity;
  altering SDK private pipelines violates repository constraints.
- **Evidence**: [Live wire reference](https://ai.google.dev/api/live),
  [SoXR streaming](https://python-soxr.readthedocs.io/en/stable/index.html).
  Repository: pyproject.toml, uv.lock, streaming.py, console.py playback loop, installed
  SDK public get_output_audio_samplerate()/push_audio_sample() signatures.

## Shared loop and configuration changes

- **Decision**: Shared orchestration remains in huggingface_realtime.py behind the existing
  ConversationHandler boundary. Deliberately start fresh Gemini sessions for profile/voice/
  tool/instruction changes; invalidate handles and announce fresh context.
- **Rationale**: Reuse interruption, memory, permissions, and tool failure behavior. Gemini
  initial socket setup is not HF's mutable session.update mechanism. Fresh sessions on
  memory/setup changes are our consistency policy; provider pause/resume can support some
  non-model changes, so immutability is not used as the sole technical justification.
- **Alternatives considered**: Endpoint substitution does not translate protocol semantics;
  copying the HF loop or building a plugin registry adds unnecessary maintenance.
- **Evidence**: [Configuration reference](https://ai.google.dev/api/live). Repository:
  conversation_handler.py, huggingface_realtime.py, main.py factory, prompts.py, console.py.

## Audio, transcription, and interruption

- **Decision**: Send mono PCM16 little-endian input tagged with actual sample rate. Decode
  advertised output rate and convert to SDK playback rate. Enable both transcript directions;
  consume every content part. Configurable standard-model defaults: gemini-3.8-live and Kore.
  Extended-thinking behavior is outside the initial supported path.
- **Rationale**: Google documents native 16 kHz input, ordinarily 24 kHz output, and input
  resampling. Devices cannot be assumed to play at 24 kHz. One message can contain multiple parts.
- **Decision**: Retain local VAD ducking/movement and Gemini automatic activity detection.
  Use an ordered interrupted -> turnComplete barrier, processing control flags before bundled
  media, and tag queued output at receipt. generationComplete alone never reopens output.
- **Rationale**: The wire reference distinguishes generation completion from interruption
  and turn completion. Input transcription is independently ordered; it is not an output barrier.
- **Decision**: Explicit app interrupt without a correlated remote boundary invalidates the
  connection/handle and visibly starts fresh. Missing interrupted-turn completion for five
  seconds uses the same safe reset. Normal server barge-in preserves context.
- **Alternatives considered**: Empty terminating clientContent also requests generation,
  so it is not a stop acknowledgement. Waiting indefinitely freezes recovery. Reopening
  output after a local epoch change alone can reclassify abandoned chunks as new output.
- **Evidence**: [Live wire reference](https://ai.google.dev/api/live),
  [capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities).
  These are design inferences with specified sequence tests, not validated robot behavior.

## Tools, images, and memories

- **Decision**: Manually dispatch effective enabled tools through existing permissions and
  manager. Preserve call IDs; map unsupported/overlong names to deterministic collision-free
  aliases using a conservative letters/digits/underscore/dash subset, maximum 128 characters.
  Validate declarations using the supported parametersJsonSchema subset before setup.
- **Rationale**: Installed Space names and schemas cannot be blindly forwarded. Nonblocking
  calls with SILENT completion preserve needs_response=False. Multiple calls and cancellation
  IDs require independent tracking; cancellation does not undo already-started robot actions.
- **Alternatives considered**: Automatic SDK execution bypasses app lifecycle controls;
  silently dropping unsupported tools gives misleading personality capabilities.
- **Decision**: One permitted camera request sends one JPEG; remove b64_im from text output
  and logs. Reuse existing memory store and prompt injection; explicit instruction refresh
  creates a fresh Gemini session. Never resume stale prompt context after refresh.
- **Rationale**: Shared saved facts are explicitly approved scope, unlike live-history copying.
  Current global memory enable controls injection; remember/forget tool access controls mutation.
- **Evidence**: [Live tools](https://ai.google.dev/gemini-api/docs/live-api/tools),
  [function schema reference](https://ai.google.dev/api/generate-content),
  [capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities).
  Repository: tools/camera.py, tools/remember.py, tools/forget.py, prompts.py,
  tools/background_tool_manager.py and effective profile toolset loading.

## Session lifetime, recovery, and replay

- **Decision**: LocalStream owns an in-memory RealtimeSessionState defined in the shared
  realtime module, passing the same object to replacement handlers during same-config retry.
  It retains logical identity, latest eligible handle and invocation ledger. Socket shutdown
  does not destroy it; fresh-session selection disposes it. Generation counters are owned
  by LocalStream across fresh states, so stale callbacks cannot collide with new ownership.
- **Rationale**: The current handler factory constructs replacement handlers; storing the
  sole ledger/handle inside those instances would lose it on retry. Invocation IDs must
  remain deduplicated when a provider resumes the same logical conversation.
- **Alternatives considered**: Persisted handles add retention risk; a second global registry
  duplicates lifecycle management. Retaining only a socket-local ledger cannot prevent replay
  across handler replacement.
- **Decision**: Both providers automatically retry recoverable failures indefinitely using
  1/2/4/8/16/30... second waits. One scheduler in LocalStream owns attempts, cancellation and
  deadlines; remove nested HF retries. Manual Retry expedites but never forks the scheduler.
  Reset backoff after a completed exchange, not merely a flapping setup acknowledgement.
- **Rationale**: This supersedes the earlier manual-Gemini policy through explicit user
  clarification. HF retry timing now deliberately follows the agreed common policy; its
  default provider/settings/voice behavior is retained.
- **Decision**: Temporary network/service failures and transient rate limits retry. Invalid
  credentials/configuration, denied access and hard billing/quota depletion await correction.
  Connect/setup share 15 seconds; sends and graceful close each have five seconds. GoAway
  warns and serially reconnects without overlapping ownership. Invalid resume visibly starts
  fresh, sharing the same attempt deadline. Configuration/prompt changes clear eligibility.
- **Rationale**: Compression/resumption span service lifetime limits; a 15-minute trial cannot
  assume one socket. A false resumability update cannot safely be replaced with an older
  checkpoint. Unknown action effects are uncertain, never automatically repeated.
- **Alternatives considered**: Finite retries conflict with the user's chosen indefinite
  policy. Blind retry of permanent client/billing errors repeats unfixable requests. Treating
  fresh-session fallback as automatic provider switching confuses continuity with provider choice.
- **Evidence**: [Session management](https://ai.google.dev/gemini-api/docs/live-api/session-management),
  [Google troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting), and current
  console.py handler construction/startup loop. Google generally recommends bounded retries;
  the indefinite policy here is the user's explicit requirement, not a provider recommendation.

## Settings, credentials, and compatibility

- **Decision**: Add optional fields to AppSettings version 1, retain old HF startup voice,
  and introduce Gemini overrides without rewriting profiles or changing HF voice resolution.
  Use existing atomic merge.
  GEMINI_API_KEY stays in private environment configuration, never RPC/settings.json.
- **Rationale**: Old installations must default to HF; saved Gemini voices cannot overwrite
  HF catalog choices. Gemini precedence is saved override, compatible personality voice,
  environment, Kore; an incompatible personality requires a saved override instead of silent
  fallthrough. Provider-specific model/voice access is checked at connection setup.
- **Alternatives considered**: Another settings file duplicates persistence. UI writes to
  .env revive quoting problems documented in settings_store.py. Reviving obsolete env names
  would unexpectedly activate stale robot configuration.
- **Evidence**: settings_store.py, startup_settings.py, config.py obsolete-env handling,
  console.py backend.config and static/js/views/settings.js.

## Design resolution and validation prerequisites

Protocol, lifecycle, sample rates, dependency choice, memory refresh, tool mapping, and
settings migration are resolved above. Constitution 2.0.0 and the user's explicit choice
set Python 3.12 as minimum. Implementation must align requires-python, dependency lock,
installation guidance and older repository statements, then validate the actual minimum.
Leaving >=3.11 metadata or merely restricting syntax is no longer an accepted resolution.
Issue agreement, service/account eligibility, usage/data budget, hardware wheel availability,
measured robot acceptance, and full repository gate health remain implementation/review
prerequisites, not unresolved architecture choices or claimed results.
