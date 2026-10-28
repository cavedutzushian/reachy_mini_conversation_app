# Contract: Provider Selection and Status

Extend existing JSON-RPC over WebSocket at /rpc. These proposed additions are not implemented
by planning. Existing HF request shapes remain valid.

## backend.config

Optional fields: backend (huggingface/gemini), hf_mode, hf_host, hf_port, gemini_model,
gemini_voice. Missing backend retains current selection; a legacy request containing HF
fields without backend selects/configures HF for backward compatibility. Update only
requested fields and never erase the other provider's settings.

Validate types and explicit provider/model/voice choices before writing settings. Validate
HF host and port with existing rules. Unknown provider-specific fields cannot become
credential storage. No api_key parameter is accepted or returned. GEMINI_API_KEY is configured
through the existing private environment path.

Success retains {ok,message,...status} shape and schedules serialized restart. Selecting
Gemini without a key is a valid saved choice but leaves waiting_for_config with corrective
instructions and manual HF selection available. Remote authentication/model access errors
are normalized after startup: local validation cannot establish account eligibility.
Save success is not a claim that connection succeeded.

## backend.retry (new)

No arguments. Schedule retry of the current provider/configuration and return
{ok:true,message,...status}. Serialize with switching; repeated clicks cannot create
concurrent sockets. Retry may restore only a valid same-config Gemini logical session.
Never silently select another provider. Response is scheduling acknowledgement, not connection success.

## status.get additions and retained fields

| Field | Meaning |
| --- | --- |
| backend | Selected effective provider |
| backend_connected | True only after setup acknowledgement |
| backend_connection_state | Existing waiting_for_config/connecting/connected/disconnected/restart_required |
| backend_error | Safe actionable text or null |
| backend_error_reason | Stable normalized reason or null |
| backend_context_state | new/resumed/unavailable |
| gemini_model / gemini_voice | Effective non-secret Gemini choices |
| gemini_key_configured | Boolean, never key value |

Preserve existing HF status fields. Never expose credentials, raw service payloads,
key-bearing URLs, handles, or base64 images. Error reasons include invalid_backend,
invalid_params, missing_gemini_key, invalid_gemini_model, invalid_gemini_voice,
authentication_failed, access_unavailable, quota_exceeded, connection_lost,
resume_unavailable, tool_schema_unsupported. Use existing JsonRpcError conventions
(-32602 for invalid parameters); asynchronous connection errors appear in status.

## Existing voices, personalities, and memory actions

voices.list/current/apply use the selected provider's catalog and override. Gemini voice
changes may reconnect with visibly fresh context; HF retains existing live-update behavior.
Provider-specific saved voice overrides never rewrite another catalog choice or profile.md.
Personality/toolset changes use existing restart. Instruction refresh invalidates Gemini
handles and explains fresh context. Global camera and --no-camera remain authoritative.

## Settings UX

Provider selector defaults to HF on an untouched installation and displays only the selected
provider's controls. Gemini setup explains the private key, eligible service access, potential
charges, and that audio, requested snapshots, and enabled shared saved memories reach the
selected service. Errors leave Retry and manual selection usable. Context continuity
(resumed/fresh) is visible. No automatic fallback or implementation terminology in user flows.
