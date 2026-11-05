---
title: Reachy Mini Conversation App
emoji: 🎤
colorFrom: red
colorTo: blue
sdk: static
pinned: false
short_description: Talk with Reachy Mini!
suggested_storage: large
tags:
 - reachy_mini
 - reachy_mini_python_app
---

# Reachy Mini conversation app

Conversational app for the Reachy Mini robot combining realtime voice, vision, personality-aware tools, and choreographed motion.

![Reachy Mini Dance](docs/assets/reachy_mini_dance.gif)

## Table of contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the app](#running-the-app)
- [LLM tools](#llm-tools-exposed-to-the-assistant)
- [Creating and adding tools](#creating-and-adding-tools)
- [Advanced features](#advanced-features)
- [Contributing](#contributing)
- [License](#license)

## Overview

- Low-latency audio conversation through the Hugging Face realtime backend, using the built-in server or a local endpoint.
- Vision is handled by the realtime backend when the `camera` tool is used.
- Layered motion system queues primary moves (dances, emotions, goto poses, breathing) while blending speech-reactive wobble.
- Async tools integrate motion, camera capture, and MCP Tool Spaces. The optional web UI (`--ui`) manages conversations, personalities, tools, and settings, and its Talk view can show the live transcript. The backend's per-turn latencies appear there when **設定 → 開發者選項 → 顯示回覆延遲** is on; the choice is saved across launches.

## Architecture

The app connects the user, AI services, and robot hardware:

<p align="center">
  <img src="docs/assets/conversation_app_arch.svg" alt="Architecture Diagram" width="600"/>
</p>

## Installation

Python 3.12 or newer is required.

> [!IMPORTANT]
> Install [Reachy Mini's SDK](https://github.com/pollen-robotics/reachy_mini/) before using this app.<br>
> Windows support is currently experimental and has not been extensively tested. Use with caution.

On Windows, the conversation loop uses `SelectorEventLoop` to avoid a Python 3.12 Proactor
TLS shutdown error (`WinError 10022`). Other platforms and the process-wide event-loop policy
keep their defaults. Custom tools running on this loop cannot use asyncio subprocess or pipe
APIs on Windows; run blocking subprocess work with `asyncio.to_thread` instead.

Daemon tools read HTTP responses before closing their connections to avoid resets on
Windows daemons. These requests connect directly to the SDK-selected daemon host without
environment proxies or automatic retries of action requests.

Connected microphone chunks are combined when sends are delayed, preserving continuous
speech with up to 250 ms of pending audio. Longer backlogs drop the oldest pending samples
with a warning. Muting or replacing a connection discards its pending microphone audio.

<details open>
<summary>Using uv (recommended)</summary>

Set up with [uv](https://docs.astral.sh/uv/):

```bash
# macOS (Homebrew)
uv venv --python /opt/homebrew/bin/python3.12 .venv

# Linux / Windows (Python in PATH)
uv venv --python python3.12 .venv

source .venv/bin/activate
uv sync --python 3.12
```

Include dev dependencies:
```bash
uv sync --group dev
```

</details>

> [!NOTE]
> Run `uv sync --frozen` to install the exact dependency set from `uv.lock` without re-resolving versions.

The optional local document retrieval dependencies can be installed with `uv sync --extra rag`.
This installs Chroma, Sentence Transformers and PyTorch; uv selects CPU PyTorch wheels on
Windows and Linux. Model files and document indexes are supplied separately and are not
downloaded by this command. The retrieval tool is not enabled by installing the extra.
Without the extra, normal conversation does not require these dependencies.
Document retrieval reads `REACHY_MINI_DOCUMENT_INDEX_PATH` (one complete prebuilt Chroma
package) and `REACHY_MINI_DOCUMENT_MODEL_PATH` (the matching local BGE-M3 model directory)
at startup. Relative paths resolve from the launch directory. Both default to unset;
URLs are rejected. Stop the app before replacing a complete package, then restart.
Changing the environment during a conversation does not replace the selected document.

Enable `search_document` for the selected personality under Tools → Tool access. It is
optional and disabled by default; ordinary conversation still works without a document.
Supply a complete `manifest.json` and `chroma/` directory conforming to the
[index package contract](specs/004-single-document-rag/contracts/index-package.md) and
[manifest schema](specs/004-single-document-rag/contracts/index-manifest.schema.json).
An external preparation step must supply all chunks, source locators, dense normalized
1024-dimensional vectors, file checksums, exact runtime versions, a matching reference
embedding and a calibrated cosine distance limit. The app has no index builder or uploader.
Only the stated document and version are searchable; other files and URLs are not tool inputs.

The first query starts a local CPU worker and can report not ready; ask again after loading.
The original query, including whitespace, is limited to 500 Unicode characters. Results
contain up to three original passages totaling 2,000 characters, with document identity,
version and source locators. A distance miss reports no evidence. A query has ten seconds
and no waiting queue: a timed-out CPU job stays busy until it actually finishes. Timeout
shows one local Traditional Chinese text notice without a spoken follow-up; interruption,
cancel, tool disable or conversation replacement discards old results and notices.

The worker uses a disposable copy of the index and never rebuilds or migrates it. Shutdown
waits at most nine seconds (5 normal, 2 terminate, 2 kill); an unconfirmed exit preserves the
copy and logs `cleanup_incomplete`. Model encoding and search stay local, but retrieved
passages are sent to the selected conversation provider and may appear in its existing
transcripts. RAG diagnostic logs redact questions and passages. Treat document content as
untrusted reference text; it grants no robot, camera or memory permissions. Hugging Face
remains the default. Gemini requires an explicitly supported asynchronous Live model;
unsupported scheduling fails setup without switching model or provider.

Real document accuracy, CPU performance and voice acceptance require separately supplied
assets and approval. The [acceptance guide](specs/004-single-document-rag/quickstart.md)
includes opt-in local checks; passing offline tests does not establish these results.

<details>
<summary>Using pip</summary>

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Install dev dependencies:
```bash
pip install -e .[dev]                   # Development tools
```

</details>

## Configuration

The default setup uses the Hugging Face backend and does not require an API key.

### Optional Gemini conversation

In Settings, enter your Gemini Developer API key directly in **Gemini 金鑰** and
choose **驗證並套用**. No separate page or popup is required. Key operations are
submitted separately from ordinary connection settings. The field is masked,
never filled with an existing key, and cleared after submission, cancellation or leaving Settings.
Validation checks the selected Live model without sending a user turn, audio,
personality, memory or tools. It does not select Gemini or interrupt active Hugging Face.
Select Gemini separately when you want to use it.
If checking key status times out, choose **重新查詢金鑰狀態** to retry manually;
key changes are never resent automatically.

Keys entered through this page survive App restarts in the current OS user's protected
credential store: Windows Credential Manager (local-machine persistence), macOS Keychain,
or Linux Secret Service. Linux needs a working user D-Bus session and an unlocked
Secret Service collection. Unsupported or locked stores fail explicitly; no plaintext,
browser storage or alternate keyring backend is used. Existing environment-only deployments
still work without a credential service. An entry for this instance that cannot be read
blocks Gemini instead of silently trying the environment key. If this happens at startup,
unlock or repair the store and restart the App before explicitly retrying.

The saved page key takes precedence over `GEMINI_API_KEY` from the existing private `.env`
or startup environment; this feature never changes that file. You may also select Gemini
with `REACHY_MINI_CONVERSATION_BACKEND=gemini`. The default `GEMINI_MODEL` is `gemini-3.8-live`.
API usage may incur charges. Vertex AI and additional providers are outside this feature.
Saved settings override environment selection. Hugging Face remains the default and its
connection and voice settings are retained when switching.

Credential management is available only from the App's direct local HTTP entry, using
`localhost`, `127.0.0.1` or `[::1]`, including supported local Control App embedding.
Unrecognized or unsupported embedding keeps key management read-only; ordinary settings
keep their existing Control App and remote access. Remote or relay-only
views show safe status and direct you to the computer running the App; your laptop's
localhost is not the robot's localhost. Unsupported WebViews should use a local browser.
Do not expose credential routes through an unauthenticated forwarding proxy.

A successful update replaces the original only after validation and protected saving.
An active Gemini conversation stops before validation and starts fresh after success;
failed validation/saving keeps the original setting and shows whether manual recovery is needed.
Clearing stops Gemini, deletes this feature's tracked credentials, and shows whether an
environment source remains. **It always requires explicit retry/reselection before reconnecting**,
including after restarting the App; local deletion does not revoke the key in your Google account.
A failed deletion remains stopped and reports incomplete/unknown state. Neither operation
changes camera, memory, personality, language, voice or tool permissions.

Credential scope follows the SDK instance path. For standalone CLI use, it follows
`REACHY_MINI_INSTANCE_PATH`, or the same platformdirs `reachy_mini/conversation_app` default;
it does not migrate legacy configuration. Use different instance paths for independent Apps.
Only one process may manage an instance's credentials at a time. The instance-local
`gemini-credential.json` contains transaction references and the reconnect gate, never a key.
Do not delete this journal to clear a credential: use the page so protected entries are removed too.
Status, errors, logs and transcripts never return the key, its suffix or a fingerprint.
OS account protection does not protect against other malicious programs running as that same user.

Gemini voice precedence is saved Gemini voice, compatible personality voice,
`GEMINI_VOICE`, then `Kore`. A personality with an incompatible voice requires a saved
Gemini voice selection. Changing the Gemini voice never rewrites the HF startup voice.

The selected service receives microphone audio, requested camera snapshots, and enabled
shared saved memories. Camera use is on demand; no continuous video is sent. Global camera
controls and `--no-camera` apply. Existing memory storage, retention and deletion are shared.
Disabling remember/forget tools blocks those actions but does not disable saved-memory recall;
use the global memory switch to disable memory injection and mutation.

Both providers automatically reconnect after transient failures, waiting 1, 2, 4, 8, 16,
then 30 seconds indefinitely. Retry expedites one attempt. Invalid configuration, credentials,
access and hard quota/billing failures wait for correction. There is no automatic provider
switch. Connection setup has a 15-second deadline, sends 5 seconds and graceful close 5 seconds.

Gemini can resume an eligible unchanged conversation using an in-memory checkpoint. A rejected
checkpoint, explicit app interruption, or model/voice/personality/tool/memory change starts
fresh context, shown in the conversation and settings. Switching providers transfers no live
history, and stops active and queued primary movements through the shared movement queue.
An uncertain robot action is reported and never automatically repeated. Normal
spoken barge-in retains context while discarding interrupted output.

Copy `.env.example` to `.env` when you want to point Hugging Face at your own local endpoint.

| Variable | Description |
|----------|-------------|
| `REALTIME_TRANSCRIPTION_LANGUAGE` | Conversation language for every personality. Defaults to `auto` for automatic language detection; set to a backend-supported code such as `en` for English or `zh` for Chinese to fix the language. A fixed language forces speech recognition and synthesis, and the model uses it as its default for greetings and replies, with explicit per-response language requests taking priority. |
| `LOCAL_BARGE_IN_ENABLED` | Local audio interruption. Defaults to `true`; requires `LOCAL_VAD_ENABLED=true`. |
| `LOCAL_VAD_ENABLED` | Local Silero speech detection for faster physical listening reactions. Defaults to `true`; set to `false` to use server VAD alone for movement. |
| `HF_REALTIME_CONNECTION_MODE` | Hugging Face connection selector: `deployed` uses the built-in Hugging Face server; `local` uses `HF_REALTIME_WS_URL`. Defaults to `deployed`. |
| `HF_REALTIME_WS_URL` | Direct websocket endpoint for your own Hugging Face backend. Accepts either a base URL like `ws://127.0.0.1:8765/v1` or the full websocket URL `ws://127.0.0.1:8765/v1/realtime`. Used when `HF_REALTIME_CONNECTION_MODE=local`. |
| `HF_TOKEN` | Optional token for Hugging Face access. Local endpoints receive only this explicitly configured token. |
| `REACHY_MINI_APP_TIMEOUT_MINUTES` | Minutes of inactivity before Reachy goes to sleep and the app stops. Defaults to `1440` (one day); set to `0` to disable. |
| `REACHY_MINI_INSTANCE_PATH` | Directory for this instance's data: long-term memory, user personalities and settings. Defaults to `conversation_app` beside the daemon's own config (`~/.config/reachy_mini` on Linux). Data written by an older version inside the installed package is copied over once. |
| `REACHY_MINI_MEMORY_ENABLED` | Long-term memory. When `false`, remembered facts stay on disk but are not injected into the prompt, and the `remember` / `forget` tools decline. Defaults to `true`. |
| `REACHY_MINI_CAMERA_ENABLED` | Camera tool. `--no-camera` forces it off regardless. Defaults to `true`. |

These variables are the starting value. Nonsecret preferences changed through the settings UI
(or from the mobile app) are written to `settings.json` in the instance directory
and wins over them, so a toggle always does what it says.

Pick the conversation language with the flag button next to the personality on the Talk view. **儲存範圍** chooses between the active personality only and all personalities; saving for all also clears the languages saved for single personalities. A personality's own language wins over the shared one and applies from the startup greeting on, so switching personality switches the language with it. Saving reconnects the conversation, and Reachy greets you again in the new language.

The app's own interface uses Traditional Chinese, independently of the conversation language. Both Hugging Face and Gemini are instructed to prefer Traditional Chinese when replying in Chinese. The existing `zh` code is displayed as **中文（繁體優先）**; `auto` remains automatic language detection, and unset or non-Chinese settings retain their existing defaults. An explicit request for another language, Simplified Chinese, translation or verbatim quotation takes priority for that response. URLs, code, paths, identifiers and specified names are preserved. Replies and user/assistant transcripts, including partial text, display the service's original text without conversion or translation. Simplified text may still appear; the app does not regenerate replies or repeat tools to correct it, and it does not rewrite saved memories or personality files.

`LOCAL_VAD_ENABLED` defaults to `true`. Change **本機語音偵測** in the gear-wheel **設定 → 語音行為** view. Saved choices take precedence over environment defaults and persist across launches; saving reconnects the conversation to apply the change. Local Silero VAD and server VAD both control physical listening: either detector freezes the antennas and suppresses idle movement. Movement resumes smoothly once both report silence. Local detection holds through 400 ms of silence and clears after 500 ms without microphone frames. Model history clears after each completed speech segment and after 500 ms of consecutive low-confidence idle audio (512 ms at the 32 ms inference cadence). These resets preserve pending microphone samples and context during speech and within-segment pauses. It uses the SDK's 16 kHz microphone audio; conversation turns continue to use server VAD. If local detection fails, the app logs a warning and uses server VAD alone.

Local barge-in defaults to enabled. Change **本機插話** in **設定 → 語音行為**, or set `LOCAL_BARGE_IN_ENABLED=false` to disable it when no saved preference exists. It requires local speech detection; disabling that switch also disables local interruption while preserving the saved barge-in preference. While audio is buffered or being submitted for playback (plus a 100 ms trailing margin), a Silero speech candidate lowers upcoming playback to 25% amplitude. Playback only stops once server VAD confirms the user turn, so loud background speech ducks the robot without dropping its answer; late audio from the interrupted response is discarded. A rejected candidate restores normal volume after 64 ms of silence. Server interruptions remain enabled, and microphone audio continues streaming to the backend. Playback is fed to the SDK in paced 20 ms chunks; already-submitted audio and SDK/transport latency delay audible volume changes. This is experimental: speaker echo, motor noise, audible latency and CPU overhead still need robot testing. With `--debug`, open `/static/vad-monitor.html` on the app settings server for a read-only live monitor with completed user and robot transcripts. The transcript view keeps the last 100 turns received while the page is open and clears on refresh. The `/rpc` WebSocket emits `conversation.vad` diagnostics with a Unix timestamp, the latest Silero speech probability, local/server/combined listening states, barge-in candidate and playback gain. Probability updates are limited to 10 Hz; state changes are reported immediately. Diagnostics reuse existing inference and do not change the inactivity timer.

On the first startup with local VAD enabled, the app downloads the [Silero VAD v6.2.1 model and MIT license](https://github.com/snakers4/silero-vad/tree/v6.2.1) directly from the pinned upstream commit and verifies their SHA-256 checksums. They are stored in the Hugging Face assets cache (`HF_HOME/assets`, or `HF_ASSETS_CACHE` when set), like the cached emotion recordings. Later starts reuse the files without a network request. The model runs on CPU with ONNX Runtime. If the download or model load fails, the app logs a warning and continues with server VAD alone.

### Hugging Face Connection Modes

Use the built-in Hugging Face server through the app-managed Space proxy. This is the default for a new install; set it explicitly only when you want to switch back from a saved local endpoint:

```env
HF_REALTIME_CONNECTION_MODE=deployed
```

Deployed session allocation falls back to cached `hf auth login` credentials and reports the daemon-provided hardware ID when available. Cached credentials and the hardware ID are not sent to local endpoints.

Run your own realtime voice backend using [speech-to-speech](https://github.com/huggingface/speech-to-speech) on the same machine as the conversation app:

```env
HF_REALTIME_CONNECTION_MODE=local
HF_REALTIME_WS_URL=ws://127.0.0.1:8765/v1/realtime
```

Run your own Hugging Face backend on your laptop and connect to it from Reachy Mini Wireless over the same Wi-Fi network:

```env
HF_REALTIME_CONNECTION_MODE=local
HF_REALTIME_WS_URL=ws://<your-laptop-lan-ip>:8765/v1/realtime
```

For that LAN setup, make sure the backend listens on an address reachable from the robot, not only on `127.0.0.1`.

If the backend stays bound to loopback on your laptop, you can forward it into the robot over SSH instead:

```bash
ssh -N -R 8765:127.0.0.1:8765 <robot-user>@<robot-host>
```

Then set this on the robot:

```env
HF_REALTIME_CONNECTION_MODE=local
HF_REALTIME_WS_URL=ws://127.0.0.1:8765/v1/realtime
```

In the web UI's Settings view, the Connection section lets you choose either the built-in server or a local `host:port` target. The UI writes `HF_REALTIME_CONNECTION_MODE` for you, and the local path writes `HF_REALTIME_WS_URL` with a default of `localhost:8765`.

## Running the app

Activate your virtual environment, then launch:

```bash
reachy-mini-conversation-app
```

> [!TIP]
> Make sure the Reachy Mini daemon is running before launching the app. If you see a `TimeoutError`, it means the daemon isn't started. See [Reachy Mini's SDK](https://github.com/pollen-robotics/reachy_mini/) for setup instructions.

The app runs in console mode. Add `--ui` to serve the web interface at http://127.0.0.1:7860/.

### CLI options

| Option | Default | Description |
|--------|---------|-------------|
| `--no-camera` | `False` | Run without camera capture. |
| `--ui` | `False` | Serve the web UI at http://127.0.0.1:7860/, in addition to console mode. |
| `--robot-name` | `None` | Optional. Connect to a specific robot by name when running multiple daemons on the same subnet. See [Multiple robots on the same subnet](#advanced-features). |
| `--debug` | `False` | Enable verbose logging for troubleshooting. |

### Examples

```bash
# Audio-only conversation (no camera)
reachy-mini-conversation-app --no-camera

# Launch with the minimal web UI for personality/mic/settings control
reachy-mini-conversation-app --ui
```

## LLM tools exposed to the assistant

The default profile exposes these tools. Use Tools → Tool access to customize any profile.
Every bundled profile enables `head_tracking` by default; users can still disable it per personality.

| Tool | Action | Dependencies |
|------|--------|--------------|
| `dance` | Queue a dance from `reachy_mini_dances_library`. | Core install only. |
| `stop_dance` | Clear queued dances. | Core install only. |
| `play_emotion` | Play a recorded emotion clip via Hugging Face datasets. | Core install only. Uses the default open emotions dataset: [`pollen-robotics/reachy-mini-emotions-library`](https://huggingface.co/datasets/pollen-robotics/reachy-mini-emotions-library). |
| `stop_emotion` | Clear queued emotions. | Core install only. |
| `camera` | Capture the latest camera frame and analyze it with the selected realtime backend. | Core install only. Requires the camera (disable with `--no-camera`). |
| `idle_do_nothing` | Explicitly remain idle during an idle turn. Not intended for normal conversation turns. | Core install only. |
| `move_head` | Queue a head pose change (left/right/up/down/front). | Core install only. |
| `head_tracking` | Follow the user's face with the head, or stop following. | Core install only. Requires a daemon with the `vision` extra and a camera. |
| `go_to_sleep` | Run Reachy's sleep movement and stop the current app after an explicit user request. | Core install only. |
| `sweep_look` | Sweep Reachy's head left, right, and back to center. | Shared tool, enabled by default in the default profile. |
| `remember` | Save one short, stable fact about the user for future sessions. | Core install only. Stored in the app instance data directory. |
| `forget` | Remove a saved memory fact by its memory ID or a short query. | Core install only. |
| `volume_control` | Read or change Reachy's speaker or microphone volume. | Core install only. Uses the daemon REST API; setting the speaker volume plays a short confirmation sound. |
| `robot_status` | Read one status topic: `name`, `software` (version, update available), `wifi` (IP address, network), `account` (Hugging Face sign-in), `imu` (which way the head is tilted, motion, temperature), `apps` (installed apps). | Core install only. Uses the daemon REST API. The update check and the Wi-Fi network details are wireless-version only; the IP address is reported on any robot. |
| `pollen_robotics_reachy_mini_search_tool__search_web` | Search the web and return a short list of results. | Preinstalled MCP Space: `pollen-robotics/reachy-mini-search-tool`. |
| `pollen_robotics_reachy_mini_weather_tool__get_weather` | Report today's weather for a place: current conditions, high and low temperature, and rain chance. | Preinstalled MCP Space: `pollen-robotics/reachy-mini-weather-tool`. |
| `pollen_robotics_reachy_mini_time_tool__get_time` | Report the current time for a timezone or the user's local time, or the difference between two timezones. | Preinstalled MCP Space: `pollen-robotics/reachy-mini-time-tool`. |
| `pollen_robotics_reachy_mini_knowledge_tool__get_info` | Read the official overview, capabilities, versions, and prices for a Pollen Robotics product or the company. | Preinstalled MCP Space: `pollen-robotics/reachy-mini-knowledge-tool`. |
| `pollen_robotics_reachy_mini_knowledge_tool__search_docs` | Search the official Reachy Mini FAQ and troubleshooting documentation. | Preinstalled MCP Space: `pollen-robotics/reachy-mini-knowledge-tool`. |

Volume writes allow up to ten seconds for the daemon's confirmation sound. If the write
response is lost, the tool reads back the level once without repeating the write. A matching
level confirms the setting; an unverified result is reported as uncertain and asks for user
direction before another attempt. Gemini retains that uncertainty in its action ledger.

> [!NOTE]
> `remember`/`forget` facts are stored in `memory.v1.json` inside the app's instance data directory (`~/.local/share/reachy_mini_conversation_app/` by default, or the instance path used by the desktop launcher). Saved memory context includes IDs so `forget` can select a fact even if a spoken query uses a different language or Chinese script. An unknown ID reports failure without falling back to a text match. Query-only calls still use case-insensitive substring matching without translation. To reset all remembered facts, delete this file.

## Creating and adding tools

Tools can run locally as Python code or remotely in an MCP-compatible Hugging Face Space. Keep robot, camera, and local-data operations in local tools. A Space is a better fit for shareable, stateless services such as search and external API lookups.

### Local tools

Create one Python module per tool, with the file name matching the tool's unique `name`. See [`idle_do_nothing.py`](src/reachy_mini_conversation_app/tools/idle_do_nothing.py) for a minimal implementation.

Each tool subclasses `Tool` and defines `name`, a model-facing `description`, an object-shaped JSON Schema in `parameters_schema`, and an async `__call__` method. Use `ToolDependencies` for runtime services, and set `needs_response = False` for actions that should not trigger a spoken follow-up. Catch expected operational failures, log them with the module logger, and return `{"error": "..."}` so the conversation can continue.

Restart the app after adding the module. Use Tools → Tool access to enable it for a personality, or add its name to that profile's `default_tools` in `profile.md`. See [External profiles and tools](#external-profiles-and-tools) for external directories and autoload behavior.

### Hugging Face Space tools

To publish a remote tool, create a Gradio Space, expose its API as MCP with `mcp_server=True`, and give each function clear type hints and docstrings. Verify that `https://<space-subdomain>.hf.space/gradio_api/mcp/schema` lists the expected tools before installing the Space.

Use the maintained [weather](https://huggingface.co/spaces/pollen-robotics/reachy-mini-weather-tool), [time](https://huggingface.co/spaces/pollen-robotics/reachy-mini-time-tool), and [search](https://huggingface.co/spaces/pollen-robotics/reachy-mini-search-tool) Spaces as examples. See Gradio's [MCP server guide](https://www.gradio.app/guides/building-mcp-server-with-gradio) for additional publishing guidance and [Installing Hugging Face Space tools](#installing-hugging-face-space-tools) for this app's installation steps.

## Advanced features

Built-in motion content is published as open Hugging Face datasets:

- Emotions: [`pollen-robotics/reachy-mini-emotions-library`](https://huggingface.co/datasets/pollen-robotics/reachy-mini-emotions-library)
- Dances: [`pollen-robotics/reachy-mini-dances-library`](https://huggingface.co/datasets/pollen-robotics/reachy-mini-dances-library)

<details>
<summary>Custom profiles</summary>

Create custom profiles with dedicated instructions and per-profile tool access.

Select and save a startup profile in the UI. The choice is stored in `startup_settings.json`. Before one is saved, `REACHY_MINI_CUSTOM_PROFILE=<name>` can select `profiles/<name>/`; otherwise the app uses `default`.

Every profile directory contains one strict schema-version-1 `profile.md`. TOML metadata is enclosed by `+++`; the remaining Markdown body is the realtime assistant prompt:

```markdown
+++
schema_version = 1
voice = "Aiden"
greeting = "Greet me warmly in one sentence, in character, and vary the wording each time."
hidden = false
default_tools = [
  "dance",
  "camera",
  "sweep_look",
]
+++

## Identity

You are a concise, friendly robot guide.
```

`schema_version`, `default_tools`, and a non-empty Markdown body are required. `voice`, `greeting`, and `hidden` are optional. Set `hidden = true` to omit a profile from the UI. An empty `default_tools` list is valid and inherits nothing.

`default_tools` is the authored baseline. Tools → Tool access stores overrides in instance-local `profile_toolsets.json` without changing bundled profiles. Restoring defaults removes the override. Active-profile changes reconnect the conversation; other changes apply when selected.

Profile directories are data-only. Python tool implementations belong in `src/reachy_mini_conversation_app/tools/`, or in `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` for external tools. Each enabled tool ID must resolve to a shared tool, an external tool, or a tool from an installed Hugging Face Space.

See [Creating and adding tools](#creating-and-adding-tools) for the local tool interface and a maintained example.

To manage personalities in the UI:

With `--ui`, Home lists the available profiles and the built-in default:

- Tap a card to apply that personality and start talking.
- Tap "Manage tools" on a saved personality to open its tool access directly.
- Tap "Custom" to create a personality with a name, instructions, and optional greeting. It inherits the default tools, which can be changed under "Manage tools". Managed instances store it at `user_personalities/<name>/profile.md`; standalone runs use `external_content/user_personalities/<name>/profile.md`.

Switching a personality reloads its prompt and effective tools through a quick backend reconnect. Editing `profile.md` directly requires re-selecting the profile or restarting the app.

</details>

<details>
<summary>Locked profile mode</summary>

To create a locked variant of the app that cannot switch profiles, edit `src/reachy_mini_conversation_app/config.py` and set the `LOCKED_PROFILE` constant to the desired profile name:
```python
LOCKED_PROFILE: str | None = "mars_rover"  # Lock to this profile
```
When set, the app ignores saved startup settings, `REACHY_MINI_CUSTOM_PROFILE`, and UI selection. The UI marks the profile as locked and disables editing.

</details>

<a id="external-profiles-and-tools"></a>

<details>
<summary>External profiles and tools</summary>

You can extend the app with profiles/tools stored outside the repository defaults.

- Core profiles are under `profiles/`.
- Core tools are under `src/reachy_mini_conversation_app/tools/`.

Recommended layout:

```text
external_content/
├── external_profiles/
│   └── my_profile/
│       └── profile.md
├── external_tools/
│   └── my_custom_tool.py
├── user_personalities/
│   └── my_custom_profile/
│       └── profile.md
├── installed_tool_spaces.json
└── profile_toolsets.json
```

Environment variables:

Set these values in your `.env` when you want env-driven external profile/tool selection:

```env
# Optional fallback/manual profile selector:
REACHY_MINI_CUSTOM_PROFILE=my_profile
REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY=./external_content/external_profiles
REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY=./external_content/external_tools
# Optional convenience mode:
# AUTOLOAD_EXTERNAL_TOOLS=1
```

Loading rules:

- Profiles: each directory requires a schema-version-1 `profile.md` with explicit `default_tools`; there is no cross-profile fallback.
- Default mode: enabled IDs must resolve to a shared, external, or installed Tool Space tool.
- Autoload: `AUTOLOAD_EXTERNAL_TOOLS=1` adds every valid `*.py` module from `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY`.
- Web UI: Tools → Tool access enables external modules per profile; it does not upload or edit Python.
- Separation: profile directories contain data only; external Python belongs in `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY`.
- Tool names: every loaded class needs a unique `Tool.name`; duplicates fail fast.

</details>

<a id="installing-hugging-face-space-tools"></a>

<details>
<summary>Installing Hugging Face Space tools</summary>

You can install MCP-compatible Hugging Face Spaces as remote tool sources for this app. Private Spaces work too, as long as `HF_TOKEN` is set (or you have run `hf auth login`) for an account that can access them. To publish a new Space, follow [Creating and adding tools](#hugging-face-space-tools).

Tools → Tool Spaces installs or refreshes a global source. Its tools then appear under Tools → Tool access for per-profile selection. Removing a Space removes its tools from every profile. Active-profile changes reconnect the conversation; other changes apply when selected.

The app accepts Hugging Face Spaces exposing the standard `/gradio_api/mcp/` endpoint, not arbitrary MCP URLs. Installation discovers the Space's tools and assigns namespaced local IDs, so do not guess or hard-code those IDs beforehand.

```bash
# install + enable in active profile
reachy-mini-conversation-app tool-spaces add <owner/space-name>

# enable in a specific profile
reachy-mini-conversation-app tool-spaces add <owner/space-name> --profile NAME

# install without enabling
reachy-mini-conversation-app tool-spaces add <owner/space-name> --install-only

# list installed spaces
reachy-mini-conversation-app tool-spaces list

# remove an installed space
reachy-mini-conversation-app tool-spaces remove owner/space-name
```

Bundled Pollen Spaces use static specs and are enabled by the default profile. Newly bundled Spaces are added to existing installations without restoring older tools the user removed. Custom Spaces are validated through the Hugging Face Hub; HF tokens are sent only to private Spaces. Tool metadata is cached in:

- `installed_tool_spaces.json` in the managed app instance directory
- `external_content/installed_tool_spaces.json` in terminal mode

Startup and profile switching read this cache without discovery or MCP probing. Network access occurs only during install, refresh, or remote tool calls. Per-profile access is stored in `profile_toolsets.json` beside the manifest, or under `external_content/` in terminal mode.

Recommended tags for discoverability on Hugging Face:

- `reachy-mini-tool`
- `mcp`

Tags are advisory; installation still requires successful MCP validation.

> [!NOTE]
> Preinstalled Pollen Spaces can be removed like any other (`tool-spaces remove pollen-robotics/reachy-mini-weather-tool`). To restore access, reinstall the Space and restore or update the relevant profile under "Tool access".

</details>

<details>
<summary>Multiple robots on the same subnet</summary>

If you run multiple Reachy Mini daemons on the same network, use:

```bash
reachy-mini-conversation-app --robot-name <name>
```

`<name>` must match the daemon's `--robot-name` value so the app connects to the correct robot.

</details>

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and [`AGENTS.md`](AGENTS.md) for coding-agent standards.

## License

Apache 2.0
