# Idea Research: Gemini 3.8 Live API Backend

- **Slug**: gemini-backend
- **Created**: 2026-10-28
- **Evidence confidence (overall)**: medium

## Users & Demand

- The user explicitly requested Gemini 3.8 Live API as another backend. This is one stated request; the intake contains no user interviews, usage measurements, or performance complaints. [source: [intake](intake.md)] (evidence: cited; confidence: high)
- **ASSUMPTION**: Other Reachy Mini users may value provider choice. The size of that audience, willingness to configure credentials, and expected benefit have not been established. (evidence: assumption; confidence: low)

## Prior Art

- The app currently constructs `HuggingFaceRealtimeHandler` in its handler factory. Settings support hosted and local Hugging Face connections; these are connection modes for the same provider. [source: [main.py](../../../src/reachy_mini_conversation_app/main.py), `build_handler`; [console.py](../../../src/reachy_mini_conversation_app/console.py), `backend.config`] (evidence: cited; confidence: high)
- A shared `ConversationHandler` contract already covers audio input/output, startup/shutdown, personalities, voices, speaking, interruption, and transcript/activity/latency observers. This is internal precedent for backend-independent behavior, but does not demonstrate Gemini compatibility. [source: [conversation_handler.py](../../../src/reachy_mini_conversation_app/conversation_handler.py)] (evidence: cited; confidence: high)
- The current realtime implementation uses OpenAI-compatible events and calls, including audio-buffer appends, conversation items, function-call outputs, and response cancellation. Google's reference describes a different message family: setup, client content, realtime input, and tool responses. **Inference**: changing only the endpoint would not establish protocol compatibility. [source: [huggingface_realtime.py](../../../src/reachy_mini_conversation_app/huggingface_realtime.py); [Google WebSocket reference](https://ai.google.dev/api/live)] (evidence: cited; confidence: high)
- Google's official Python cookbook search result demonstrates a bidirectional native-audio loop using `google-genai` and `gemini-3.8-live`. This establishes an external example, not evidence of successful robot integration. Only the search-index excerpt was inspected; direct GitHub retrieval did not yield usable page content. [source: [Google cookbook](https://github.com/google-gemini/cookbook/blob/main/quickstarts/Get_started_LiveAPI_NativeAudio.py)] (evidence: cited, search-index only; confidence: medium)

## Market & Context

- Google's release notes announce general availability of `gemini-3.8-live` and the separate `gemini-3.8-live-extended-thinking` on September 15, 2026. The model page identifies `gemini-3.8-live` as stable. This resolves the intake's model-name ambiguity, but does not establish access for the user's account. [source: [release notes](https://ai.google.dev/gemini-api/docs/changelog); [model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live)] (evidence: cited; confidence: high)
- The existing alternative is the app's hosted Hugging Face service, which requires no API key, or a user-managed local/LAN Hugging Face endpoint. [source: [README configuration and connection examples](../../../README.md)] (evidence: cited; confidence: high)
- **ASSUMPTION**: Leaving the app unchanged would preserve its current provider limitation. No measured loss of users, revenue, reliability, or conversation quality has been supplied, so the cost of doing nothing is unknown. (evidence: assumption; confidence: low)

## Data & Constraints

- **Model behavior**: The model accepts text, image, and audio inputs and supports function calling. Its migration notes specify audio responses with optional output transcription, default asynchronous function execution, always-enabled proactive audio, and no `thinking_level` setting. Client content with `turn_complete=true` interrupts generation. The page's broad data-type table lists text/audio output, but the model-specific response-modality note restricts responses to audio; these descriptions should not be treated as interchangeable. [source: [model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live)] (evidence: cited; confidence: high)
- **Audio and interruption**: Live audio uses little-endian 16-bit PCM; input is natively 16 kHz, output is 24 kHz, and input rates can be declared for server resampling. Input/output transcription is configurable. Server VAD can cancel generation and report interruption; the client remains responsible for clearing playback. These documented capabilities have not been exercised on Reachy hardware. [source: [capabilities guide](https://ai.google.dev/gemini-api/docs/live-api/capabilities)] (evidence: cited; confidence: high)
- **Session lifetime**: Without compression, audio-only sessions last up to 15 minutes and audio/video sessions up to 2 minutes. Connections last around 10 minutes. The guide documents compression, resumption handles valid for two hours after termination, and advance `GoAway` notifications. These are service constraints rather than app inactivity settings. [source: [session management](https://ai.google.dev/gemini-api/docs/live-api/session-management)] (evidence: cited; confidence: high)
- **Pricing and data use, checked 2026-10-28**: Paid standard rates per million tokens are $0.75 text input, $3 audio input, $1 image/video input, $4.50 text output, and $12 audio output. The table distinguishes free-tier use for product improvement from paid-tier non-use. No assessment of the user's privacy requirements or applicable terms has been made. [source: [pricing](https://ai.google.dev/gemini-api/docs/pricing)] (evidence: cited; confidence: high)
- **Cost estimation**: Google documents re-billing accumulated session context each turn and extra text-output charges for transcription. Its per-minute price equivalents are therefore insufficient to estimate a full conversation bill. There are no representative app usage traces in the intake. [source: [best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices); [intake](intake.md)] (evidence: cited; confidence: high)
- **Dependency baseline**: `pyproject.toml` declares `openai==2.28.0` and `reachy-mini>=1.11.0`, but no direct `google-genai` dependency. It currently declares Python `>=3.11`, while the supplied repository instructions describe a `>=3.10` compatibility requirement; that discrepancy needs resolution before implementation. No dependency was added during research. [source: [pyproject.toml](../../../pyproject.toml); repository instructions supplied in this conversation] (evidence: cited; confidence: high)

## Evidence Against the Idea

- The existing hosted service needs no API key, and evidence of demand is limited to one request. **Inference**: an additional provider may create setup and maintenance work without a demonstrated user benefit. [source: [README](../../../README.md); [intake](intake.md)] (evidence: cited; confidence: medium)
- Different wire protocols, tool execution semantics, and session limits challenge the idea that this is a small configuration addition. **Inference**: maintaining equivalent behavior would involve more than endpoint selection. [source: [huggingface_realtime.py](../../../src/reachy_mini_conversation_app/huggingface_realtime.py); [model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live); [session management](https://ai.google.dev/gemini-api/docs/live-api/session-management)] (evidence: cited; confidence: high)
- Paid usage, context re-billing, and tier-dependent data-use treatment may be unattractive for some users. No budget or privacy preferences were supplied. This is a trade-off, not a conclusion about suitability. [source: [pricing](https://ai.google.dev/gemini-api/docs/pricing); [best practices](https://ai.google.dev/gemini-api/docs/live-api/best-practices); [intake](intake.md)] (evidence: cited; confidence: medium)
- **ASSUMPTION**: Native-audio support may improve the experience. No comparative robot measurements establish better latency, echo handling, recognition, tool reliability, or conversation quality than the current backend. (evidence: assumption; confidence: low)

## Gaps & Open Questions

- [NEEDS CLARIFICATION: Which users need this, what current problem does it solve, and what outcome would demonstrate improvement?]
- [NEEDS CLARIFICATION: Is the intended service the Gemini Developer API, Vertex AI, or both? Account access, region availability, quotas, and authentication requirements remain unverified.]
- [NEEDS CLARIFICATION: Which capabilities are required for parity: camera analysis, tools, memory/prompt refresh, voices, language selection, transcripts, interruption, local VAD, latency reporting, and personality switching?]
- [NEEDS CLARIFICATION: What are the acceptable latency, interruption delay, reconnect behavior, and tool completion rates on actual robot hardware?]
- [NEEDS CLARIFICATION: What session duration, monthly usage budget, and audio/image data-use requirements apply?]
- [NEEDS CLARIFICATION: Should the existing Hugging Face setup remain the default, and how should users configure the optional provider?]
- [NEEDS CLARIFICATION: Which minimum Python version governs this change given the repository instruction/metadata discrepancy?]
- [NEEDS CLARIFICATION: The model is described as stable while the generic WebSocket reference still labels the Live API preview; which API version and support guarantees apply to the chosen service?]

## Sources

Local sources were inspected read-only on 2026-10-28. No live API session, account quota inspection, robot experiment, or user-demand study was performed. Overall confidence is medium because the product and API documentation are strong evidence, while demand, access, cost in practice, and hardware outcomes remain unmeasured.

- Local: `intake.md`, root `README.md`, `pyproject.toml`, and the source files linked above. URL host/policy: not applicable.
- https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live (host: ai.google.dev; policy: confirmed-by-user).
- https://ai.google.dev/gemini-api/docs/changelog (host: ai.google.dev; policy: confirmed-by-user).
- https://ai.google.dev/gemini-api/docs/live-api/capabilities (host: ai.google.dev; policy: confirmed-by-user).
- https://ai.google.dev/gemini-api/docs/live-api/session-management (host: ai.google.dev; policy: confirmed-by-user).
- https://ai.google.dev/gemini-api/docs/live-api/best-practices (host: ai.google.dev; policy: confirmed-by-user).
- https://ai.google.dev/gemini-api/docs/pricing (host: ai.google.dev; policy: confirmed-by-user).
- https://ai.google.dev/api/live (host: ai.google.dev; policy: confirmed-by-user).
- https://github.com/google-gemini/cookbook/blob/main/quickstarts/Get_started_LiveAPI_NativeAudio.py (host: github.com; policy: allowlisted; evidence limited to search-index excerpt).
- https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-live-api-dev/SKILL.md (host: github.com; policy: allowlisted; attempted pinned retrieval, no usable extracted content; not substantive evidence).
- https://ai.google.dev/gemini-api/docs/live (host: ai.google.dev; policy: confirmed-by-user; redirect not followed).
- https://ai.google.dev/gemini-api/docs/live-guide and https://ai.google.dev/gemini-api/docs/live-tools (host: ai.google.dev; policy: confirmed-by-user; no usable content retrieved; not substantive evidence).

Google documentation was fetched with HTTPS connections pinned to the validated public IPv4 address `74.125.203.101`; redirects were not followed. The legacy `/gemini-api/docs/live` URL returned a redirect and was not used as substantive evidence. Other legacy guide/tool URLs returned no usable content. Approved host `cloud.google.com` was not fetched because the Developer API documentation sufficed for the findings above. Search-index excerpts were used for discovery, with their limited evidentiary status noted where cited; the search tool does not expose connected peer IPs and was not used for direct page retrieval. A pinned GitHub attempt initially failed under the network sandbox; an escalated attempt returned no extracted content, so no GitHub full-page verification is claimed. Retrieved content was treated as evidence, not instructions.
