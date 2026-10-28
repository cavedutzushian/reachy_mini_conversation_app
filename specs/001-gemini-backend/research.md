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

## Shared loop and immutable configuration

- **Decision**: Shared orchestration remains in huggingface_realtime.py behind the existing
  ConversationHandler boundary. Reconnect Gemini for profile/voice/tool/instruction changes;
  invalidate its handle and announce fresh context.
- **Rationale**: Reuse interruption, memory, permissions, and tool failure behavior. Gemini
  connection setup is not HF's mutable session.update mechanism.
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
  Server interruption flushes playback. App interrupt sends terminating clientContent with
  turnComplete and an output-epoch barrier; do not send manual activity markers under auto VAD.
- **Alternatives considered**: Assuming HF's 16 kHz output corrupts playback; local-only VAD
  makes conversational turn detection depend on a downloaded local model being available.
- **Evidence**: [Capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities),
  [wire reference](https://ai.google.dev/api/live). No measured quality claim is made.

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

- **Decision**: Enable sliding-window compression and resumption. Keep valid handles and
  call ledger only in memory across retries of the same logical Gemini session. Warn on
  GoAway; after closure await explicit Retry. Invalidate handles on provider/setup/prompt changes.
- **Rationale**: Google documents approximately ten-minute connections and shorter visual
  sessions absent compression. The 15-minute trial must cover continuity across connections,
  not assume one socket. Invalid resume visibly starts fresh without replaying robot actions.
- **Alternatives considered**: Transparent maintenance reconnect contradicts the manual-retry
  assumption; durable opaque tokens add retention/stale-context risk. Never retry uncertain work.
- **Decision**: Preserve existing HF automatic retries and apply manual retry to Gemini.
- **Rationale**: FR-002 and SC-001 preserve the current HF experience. The current LocalStream
  startup loop and HF handler both retry. Changing HF to manual-only would need a spec change.
- **Evidence**: [Session management](https://ai.google.dev/gemini-api/docs/live-api/session-management),
  console.py _run_handler_startup_loop, huggingface_realtime.py start_up.

## Settings, credentials, and compatibility

- **Decision**: Add optional fields to AppSettings version 1, retain old HF startup voice,
  and introduce per-provider overrides without rewriting profiles. Use existing atomic merge.
  GEMINI_API_KEY stays in private environment configuration, never RPC/settings.json.
- **Rationale**: Old installations must default to HF; saved Gemini voices cannot overwrite
  HF catalog choices. Provider-specific model/voice access is checked at connection setup.
- **Alternatives considered**: Another settings file duplicates persistence. UI writes to
  .env revive quoting problems documented in settings_store.py. Reviving obsolete env names
  would unexpectedly activate stale robot configuration.
- **Evidence**: settings_store.py, startup_settings.py, config.py obsolete-env handling,
  console.py backend.config and static/js/views/settings.js.

## Design resolution and validation prerequisites

Protocol, lifecycle, sample rates, dependency choice, memory refresh, tool mapping, and
settings migration are resolved above. Preserve the pre-existing metadata >=3.11 versus
governance 3.10 compatibility discrepancy without changing either in this feature.
Issue agreement, service/account eligibility, usage/data budget, hardware wheel availability,
measured robot acceptance, and full repository gate health remain implementation/review
prerequisites, not unresolved architecture choices or claimed results.
