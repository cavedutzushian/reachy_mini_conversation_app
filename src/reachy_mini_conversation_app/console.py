"""Bidirectional local audio stream with optional web settings UI.

If the selected backend is missing its required API key, a settings page is
served via the Reachy Mini Apps settings server so users can configure it.
"""

import re
import sys
import json
import time
import asyncio
import hashlib
import logging
import secrets
import ipaddress
import itertools
import threading
from typing import Any, List, Optional
from pathlib import Path
from collections import deque
from urllib.parse import urlsplit
from collections.abc import Mapping, Callable

import httpx
import numpy as np
from openai import APIStatusError
from websockets.exceptions import InvalidStatus

from reachy_mini import ReachyMini
from reachy_mini.io.jsonrpc import JsonRpcError
from reachy_mini.apps.jsonrpc_server import JsonRpcServer
from reachy_mini.media.media_manager import MediaBackend
from reachy_mini_conversation_app.config import (
    HF_BACKEND,
    GEMINI_BACKEND,
    LOCKED_PROFILE,
    HF_REALTIME_WS_URL_ENV,
    GEMINI_AVAILABLE_VOICES,
    HF_LOCAL_CONNECTION_MODE,
    HF_DEPLOYED_CONNECTION_MODE,
    config,
    get_default_voice,
    get_hf_session_url,
    set_custom_profile,
    get_available_voices,
    get_hf_direct_ws_url,
    build_hf_direct_ws_url,
    has_hf_realtime_target,
    parse_hf_direct_target,
    get_hf_connection_selection,
    normalize_conversation_backend,
    refresh_runtime_config_from_env,
)
from reachy_mini_conversation_app.prompts import get_session_voice, get_session_language, get_session_instructions
from reachy_mini_conversation_app.streaming import AdditionalOutputs, audio_to_float32
from reachy_mini_conversation_app.memory_routes import register_memory_methods
from reachy_mini_conversation_app.profile_store import canonical_profile_name
from reachy_mini_conversation_app.vision_routes import register_vision_methods
from reachy_mini_conversation_app.settings_store import (
    AppSettings,
    update_settings,
    apply_settings_to_runtime,
    load_settings_into_runtime,
)
from reachy_mini_conversation_app.gemini_realtime import GeminiConnectionError, validate_gemini_candidate
from reachy_mini_conversation_app.language_routes import LanguageScope, register_language_methods
from reachy_mini_conversation_app.audio.resampling import AudioResampler
from reachy_mini_conversation_app.startup_settings import read_startup_settings, write_startup_settings
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies, get_tool_specs, initialize_tools
from reachy_mini_conversation_app.tool_space_routes import register_tool_space_methods
from reachy_mini_conversation_app.gemini_credentials import CredentialError, GeminiCredentials
from reachy_mini_conversation_app.personality_routes import (
    build_personality_ops,
    register_personality_methods,
)
from reachy_mini_conversation_app.profile_tool_routes import register_profile_tool_methods
from reachy_mini_conversation_app.audio.startup_config import apply_audio_startup_config
from reachy_mini_conversation_app.conversation_handler import VADStatus, AudioFrame, ConversationHandler
from reachy_mini_conversation_app.huggingface_realtime import (
    CLOSE_TIMEOUT_S,
    SETUP_TIMEOUT_S,
    RealtimeSessionState,
    RealtimeConversationHandler,
)


try:
    # FastAPI is provided by the Reachy Mini Apps runtime
    from fastapi import FastAPI, Request, Response
    from pydantic import BaseModel
    from fastapi.responses import FileResponse, JSONResponse
    from starlette.staticfiles import StaticFiles
except Exception:  # pragma: no cover - only loaded when settings_app is used
    FastAPI = object  # type: ignore
    FileResponse = object  # type: ignore
    StaticFiles = object  # type: ignore
    BaseModel = object  # type: ignore

logger = logging.getLogger(__name__)


def _detach_framework_root_routes(app: "FastAPI") -> None:
    """Strip framework routes that would shadow the settings UI."""
    routes = getattr(app, "router", None)
    routes = getattr(routes, "routes", None) if routes else getattr(app, "routes", None)
    if routes is None:
        return
    survivors = []
    for route in routes:
        path = getattr(route, "path", None)
        is_catch_all = isinstance(path, str) and path.startswith("/{") and path.endswith(":path}")
        if path in ("/", "/static") or is_catch_all:
            logger.debug("detaching framework-provided route %r (%s)", path, type(route).__name__)
            continue
        survivors.append(route)
    routes[:] = survivors


LOCAL_PLAYER_BACKEND = (
    getattr(MediaBackend, "LOCAL", None)
    or getattr(MediaBackend, "GSTREAMER", None)
    or getattr(MediaBackend, "DEFAULT", None)
)

HandlerFactory = Callable[[Optional[str]], ConversationHandler]

LEGACY_STARTUP_ENV_NAMES = (
    "REACHY_MINI_CUSTOM_PROFILE",
    "REACHY_MINI_VOICE_OVERRIDE",
)
BACKEND_RETRY_DELAY_SECONDS = 5.0
CONVERSATION_HISTORY_LIMIT = 200  # events, about 100 exchanges
PLAYBACK_LEAD_SECONDS = 0.1  # paced chunks reach the SDK this far ahead of their slot
MICROPHONE_BUFFER_SECONDS = 0.25


class LocalStream:
    """LocalStream using Reachy Mini's recorder/player."""

    def __init__(
        self,
        handler: ConversationHandler,
        robot: ReachyMini,
        *,
        settings_app: Optional[FastAPI] = None,
        instance_path: Optional[str] = None,
        handler_factory: HandlerFactory | None = None,
        startup_voice: Optional[str] = None,
        tool_deps: ToolDependencies | None = None,
        camera_forced_off: bool = False,
        credentials: GeminiCredentials | None = None,
    ):
        """Initialize the stream with a realtime handler and pipelines.

        - ``settings_app``: the Reachy Mini Apps FastAPI to attach settings endpoints.
        - ``instance_path``: directory where per-instance ``.env`` should be stored.
        - ``handler_factory``: builds a fresh handler for the currently selected backend.
        - ``tool_deps``: live tool dependencies, so vision.* can toggle the camera.
        """
        self._robot = robot
        self._credentials = credentials
        self._credential_hold = False
        self._credential_validation_task: asyncio.Task[None] | None = None
        self._credential_csrf = secrets.token_urlsafe(32)
        self._credential_csrf_expires = time.monotonic() + 600
        self._stop_event = asyncio.Event()
        self._playback_flush_lock = asyncio.Lock()
        self._playback_clock = 0.0  # monotonic end of audio pushed to the SDK
        self._restart_requested = asyncio.Event()
        self._tasks: List[asyncio.Task[None]] = []
        self._handler_factory = handler_factory
        self._voice_override = startup_voice
        self._settings_app: Optional[FastAPI] = settings_app
        self._instance_path: Optional[str] = instance_path
        self._tool_deps = tool_deps
        self._camera_forced_off = camera_forced_off
        self._settings_initialized = False
        self._asyncio_loop = None
        self._mic_muted = False  # mic starts live; the UI toggles it via the settings API
        self._microphone_epoch = 0
        self._audio_warming_up = False
        self._backend_connection_state = "not_started"
        self._backend_error: str | None = None
        self._backend_error_reason: str | None = None
        self._backend_retry_delay = BACKEND_RETRY_DELAY_SECONDS
        self._retry_attempt = 0
        self._retry_delay_seconds: float | None = None
        self._retry_requested = asyncio.Event()
        self._session_task: asyncio.Task[None] | None = None
        self._retired_handler: ConversationHandler | None = None
        self._transition_lock = asyncio.Lock()
        self._pending_say: str | None = None
        self._playback_resampler: AudioResampler | None = None
        self._playback_rates: tuple[int, int, int] | None = None
        self.session_state = (
            handler.session_state if isinstance(handler, RealtimeConversationHandler) else RealtimeSessionState()
        )
        # JSON-RPC control surface (mounted at /rpc in _init_settings_ui_if_needed).
        # Notifications (conversation.turn/phase/transcript/latency/activity) are pushed
        # here from activity, transcripts and latencies. Survives handler rebuilds (mounted once).
        self._rpc: Optional[JsonRpcServer] = None
        self._last_turn_state: Optional[str] = None
        # This run's final transcripts and latencies, replayed by conversation.history so a page
        # opened mid-conversation shows earlier turns. In memory only: gone when the app stops.
        self._conversation_history: deque[dict[str, object]] = deque(maxlen=CONVERSATION_HISTORY_LIMIT)
        # Seeded from the wall clock so a restarted app's events sort after those an open page has seen.
        self._conversation_seq = itertools.count(int(time.time() * 1000))
        # Per-role throttle timestamps for conversation.level (orb audio meter).
        self._last_level_emit: dict[str, float] = {}
        self._install_handler(handler)

    def _install_handler(self, handler: ConversationHandler) -> None:
        """Set the active handler and wire LocalStream-owned helpers into it."""
        self.handler = handler
        handler.session_state = self.session_state
        handler.exchange_completed = lambda: self._exchange_completed() if self.handler is handler else None
        handler.transcript_interrupted = lambda: self._dispatch_interrupted() if self.handler is handler else None
        self.handler._clear_queue = lambda: self.clear_audio_queue(handler)
        self._attach_observers_to_handler()

    def _exchange_completed(self) -> None:
        self._retry_attempt = 0

    def _dispatch_interrupted(self) -> None:
        self._publish_conversation_event("conversation.interrupted", {"role": "assistant", "state": "interrupted"})

    def _attach_observers_to_handler(self) -> None:
        """Wire the handler's activity, transcript and latency observers to JSON-RPC pushes."""
        owner = self.handler

        def activity(reason: str) -> None:
            if self.handler is owner:
                self._dispatch_activity(reason)

        def transcript(role: str, text: str, final: bool) -> None:
            if self.handler is owner:
                self._dispatch_transcript(role, text, final)

        def latency(timing: dict[str, int | str | None]) -> None:
            if self.handler is owner:
                self._dispatch_latency(timing)

        def vad(status: VADStatus) -> None:
            if self.handler is owner:
                self._dispatch_vad(status)

        setter = getattr(self.handler, "set_activity_observer", None)
        if callable(setter):
            setter(activity)
        transcript_setter = getattr(self.handler, "set_transcript_observer", None)
        if callable(transcript_setter):
            transcript_setter(transcript)
        latency_setter = getattr(self.handler, "set_latency_observer", None)
        if callable(latency_setter):
            latency_setter(latency)

        self.handler.set_vad_observer(vad)

    def _dispatch_vad(self, status: VADStatus) -> None:
        if self._rpc is not None:
            self._rpc.broadcast_threadsafe("conversation.vad", dict(status))

    def _dispatch_transcript(self, role: str, text: str, final: bool) -> None:
        """Push a conversation.transcript notification, recording final ones in the history."""
        params: dict[str, object] = {"role": role, "text": text, "final": final}
        if final:
            self._publish_conversation_event("conversation.transcript", params)
        elif self._rpc is not None:
            self._rpc.broadcast_threadsafe("conversation.transcript", params)

    def _dispatch_latency(self, latency: dict[str, int | str | None]) -> None:
        """Push a conversation.latency notification and record it in the history."""
        self._publish_conversation_event("conversation.latency", latency)

    def _publish_conversation_event(self, method: str, params: Mapping[str, object]) -> None:
        """Record one event in this run's history, then push it with its sequence number."""
        event_params = {**params, "seq": next(self._conversation_seq)}
        self._conversation_history.append({"method": method, "params": event_params})
        if self._rpc is not None:
            self._rpc.broadcast_threadsafe(method, event_params)

    # Audio level meter for the client orb. RMS is scaled into a visible 0..1
    # range and capped to ~15 Hz so it stays light on the DataChannel.
    _LEVEL_INTERVAL_S = 1.0 / 15.0
    _LEVEL_GAIN = 6.0

    def _emit_level(self, role: str, frame: Any) -> None:
        """Emit a throttled conversation.level (RMS) for ``role`` (user/assistant)."""
        if self._rpc is None:
            return
        now = time.monotonic()
        if now - self._last_level_emit.get(role, 0.0) < self._LEVEL_INTERVAL_S:
            return
        self._last_level_emit[role] = now
        try:
            samples = audio_to_float32(frame)
            rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        except Exception:
            return
        level = max(0.0, min(1.0, rms * self._LEVEL_GAIN))
        self._rpc.broadcast_threadsafe("conversation.level", {"role": role, "rms": round(level, 3)})

    # Map backend activity reasons to the orb's turn states (mirrors the old
    # browser orb's mapActivityToState so the orb reliably reaches listening/
    # thinking/speaking across the reasons the HF handler actually emits).
    # Transcript text is delivered separately via the transcript observer.
    _REASON_TO_TURN = {
        "user_speech_started": "listening",
        "user_transcription_delta": "listening",
        "user_speech_stopped": "thinking",
        "user_transcription_completed": "thinking",
        "response_created": "thinking",
        "tool_call_received": "thinking",
        "tool_result_ready": "thinking",
        "assistant_audio_delta": "speaking",
        "assistant_transcript_done": "ready",
    }

    def _dispatch_activity(self, reason: str) -> None:
        """Fan one activity reason out to JSON-RPC clients."""
        if reason in ("fresh_context", "uncertain_action", "reconnecting"):
            message = {
                "fresh_context": "正在開始新對話。",
                "uncertain_action": "先前的機器人動作可能已開始，結果不明，因此不會重複執行。",
                "reconnecting": "正在重新連接所選服務。",
            }[reason]
            self._publish_conversation_event("conversation.context", {"message": message})
        if self._rpc is not None:
            # Raw reason (the browser orb maps it exactly like the old SSE feed)...
            self._rpc.broadcast_threadsafe("conversation.activity", {"reason": reason})
            # ...plus a semantic turn state for clients without that mapping (mobile).
            state = self._REASON_TO_TURN.get(reason)
            if state and state != self._last_turn_state:
                self._last_turn_state = state
                self._rpc.broadcast_threadsafe("conversation.turn", {"state": state})

    def _emit_phase(self, phase: str, reason: Optional[str] = None) -> None:
        """Push a conversation.phase notification to JSON-RPC clients."""
        if self._rpc is not None:
            self._rpc.broadcast_threadsafe("conversation.phase", {"phase": phase, "reason": reason})

    def seconds_since_activity(self) -> float:
        """Seconds since the live handler last saw conversation activity."""
        return time.monotonic() - self.handler.last_activity_time

    def _backend_connected(self) -> bool:
        """Return whether the active handler currently has a realtime connection."""
        if isinstance(self.handler, RealtimeConversationHandler):
            return self.handler._is_connected()
        try:
            handler_state = vars(self.handler)
        except TypeError:
            handler_state = {}
        return handler_state.get("connection") is not None

    def _can_rebuild_handler(self) -> bool:
        """Return whether LocalStream can construct handlers for backend changes."""
        return self._handler_factory is not None

    def _build_handler_for_current_backend(self) -> ConversationHandler:
        """Create and install a fresh handler for the current runtime backend config."""
        if self._handler_factory is None:
            return self.handler
        handler = self._handler_factory(self._voice_override)
        self._install_handler(handler)
        return handler

    async def _shutdown_active_handler(self) -> None:
        """Best-effort shutdown for the currently active handler."""
        handler = self.handler
        if self._retired_handler is handler:
            return
        self._retired_handler = handler
        self.session_state.begin_connection()
        if self.session_state.mark_uncertain_actions():
            self._dispatch_activity("uncertain_action")
        cleanup = asyncio.create_task(handler.shutdown())
        operations = {cleanup}
        if isinstance(handler, ConversationHandler):
            operations.add(asyncio.create_task(self.clear_audio_queue(handler)))
        try:
            finished, pending = await asyncio.wait(operations, timeout=CLOSE_TIMEOUT_S)
            for operation in pending:
                operation.cancel()
                operation.add_done_callback(self._consume_retired_task)
            if pending:
                if isinstance(handler, RealtimeConversationHandler):
                    handler._abort_connection()
                logger.warning("Backend close exceeded five seconds")
            for operation in finished:
                await operation
        except asyncio.CancelledError:
            if isinstance(handler, RealtimeConversationHandler):
                handler._abort_connection()
            raise
        except TimeoutError:
            logger.warning("Backend close exceeded five seconds")
        except Exception:
            logger.warning("Backend cleanup failed")
        finally:
            for operation in operations:
                if not operation.done():
                    operation.cancel()
                    operation.add_done_callback(self._consume_retired_task)

    @staticmethod
    def _consume_retired_task(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            logger.warning("Retired backend task ended with an error")

    def _mark_restart_requested(self, reason: str) -> None:
        """Request a backend restart from a synchronous route handler."""
        logger.info("Backend restart requested: %s", reason)
        self._set_backend_connection_state("connecting")
        loop = self._asyncio_loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.request_backend_restart(reason), loop)
            return
        self._restart_requested.set()

    async def request_backend_restart(self, reason: str) -> None:
        """Ask the startup loop to rebuild the backend and stop the current handler."""
        self._set_backend_connection_state("connecting")
        self._restart_requested.set()
        async with self._transition_lock:
            provider_changed = self.session_state.provider != config.CONVERSATION_BACKEND
            if reason != "injected_speech":
                self._pending_say = None
            if self._session_task is not None:
                self._session_task.cancel()
            if self.session_state.mark_uncertain_actions():
                self._dispatch_activity("uncertain_action")
            self.session_state.fresh(config.CONVERSATION_BACKEND, "")
            if provider_changed and self._tool_deps is not None:
                self._tool_deps.movement_manager.clear_move_queue()
            self._dispatch_activity("fresh_context")
            await self._shutdown_active_handler()

    async def _sleep_or_restart_requested(self, delay: float | None) -> None:
        """Sleep for a retry interval, waking early if a restart is requested."""
        if self._restart_requested.is_set():
            return
        waits = [
            asyncio.create_task(self._restart_requested.wait()),
            asyncio.create_task(self._retry_requested.wait()),
            asyncio.create_task(self._stop_event.wait()),
        ]
        try:
            await asyncio.wait(waits, timeout=delay, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiter in waits:
                waiter.cancel()
            await asyncio.gather(*waits, return_exceptions=True)
            self._retry_requested.clear()

    @staticmethod
    def _format_backend_error(error: BaseException | str) -> str:
        """Return a compact user-facing backend error string."""
        if isinstance(error, str):
            return error
        if isinstance(error, GeminiConnectionError):
            return error.reason
        if isinstance(error, ValueError):
            if "voice" in str(error):
                return "invalid_gemini_voice"
            return "invalid_params"
        return "後端連線失敗，請檢查設定後重試。"

    def _set_backend_connection_state(self, state: str, error: BaseException | str | None = None) -> None:
        """Update backend connection status exposed through the settings UI."""
        self._backend_connection_state = state
        if error is not None:
            self._backend_error = self._format_backend_error(error)
            self._backend_error_reason = (
                self._backend_error
                if isinstance(error, (GeminiConnectionError, ValueError, str))
                else "connection_lost"
            )
        elif state != "disconnected":
            self._backend_error = None
            self._backend_error_reason = None

    def _backend_connection_status(self) -> dict[str, object]:
        """Return the backend connection state exposed in the settings API."""
        connected = self._backend_connected()
        state = "connected" if connected else self._backend_connection_state
        return {
            "backend_connected": connected,
            "backend_connection_state": state,
            "backend_error": None if connected else self._backend_error,
            "backend_error_reason": None if connected else self._backend_error_reason,
            "backend_context_state": self.session_state.context_state,
            "backend_retry_attempt": self._retry_attempt,
            "backend_retry_delay_seconds": self._retry_delay_seconds,
        }

    def _remove_persisted_env_values(self, env_names: tuple[str, ...]) -> None:
        """Remove keys from the instance `.env` without mutating the current runtime."""
        normalized_names = tuple(sorted({name.strip() for name in env_names if name and name.strip()}))
        if not normalized_names or not self._instance_path:
            return

        env_path = Path(self._instance_path) / ".env"
        if not env_path.exists():
            return

        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
            filtered_lines = [
                line
                for line in lines
                if not any(line.strip().startswith(f"{env_name}=") for env_name in normalized_names)
            ]
            if filtered_lines == lines:
                return

            final_text = "\n".join(filtered_lines)
            if final_text:
                final_text += "\n"
            env_path.write_text(final_text, encoding="utf-8")
            logger.info("Removed %s from %s", ", ".join(normalized_names), env_path)
        except Exception as e:
            logger.warning("Failed to remove %s: %s", ", ".join(normalized_names), e)

    def _save_settings(self, changes: AppSettings) -> None:
        """Persist settings chosen through the UI and apply them right away."""
        update_settings(self._instance_path, changes)
        apply_settings_to_runtime(changes)

    def _persist_hf_direct_connection(self, host: str, port: int) -> None:
        """Persist a direct Hugging Face websocket target."""
        self._save_settings(
            AppSettings(
                hf_connection_mode=HF_LOCAL_CONNECTION_MODE,
                hf_ws_url=build_hf_direct_ws_url(host, port),
            )
        )

    def _persist_hf_allocator_connection(self) -> None:
        """Persist the deployed Hugging Face allocator mode."""
        self._save_settings(AppSettings(hf_connection_mode=HF_DEPLOYED_CONNECTION_MODE))
        # Older installs kept an allocator URL in the instance .env; drop it so
        # the stored mode is what decides.
        self._remove_persisted_env_values(("HF_REALTIME_SESSION_URL",))

    def _apply_setting_with_restart(self, changes: AppSettings, reason: str) -> str:
        """Persist one setting and reconnect the backend so it takes effect."""
        self._save_settings(changes)
        if not self._can_rebuild_handler():
            return "已儲存，請重新啟動 Reachy Mini Conversation 以套用。"
        self._mark_restart_requested(reason)
        return "已儲存，正在重新連接對話以套用。"

    async def _refresh_instructions(self) -> bool:
        """Push rebuilt instructions to the live session (see memory.clear)."""
        if config.CONVERSATION_BACKEND == GEMINI_BACKEND:
            await self.request_backend_restart("instructions_changed")
            return False
        return await self.handler.refresh_instructions()

    def _set_memory_enabled(self, enabled: bool) -> None:
        """Turn long-term memory on or off, for this run and the next ones.

        The prompt builder and the memory tools read the flag live, so the
        caller only has to refresh the session instructions, not reconnect.
        """
        self._save_settings(AppSettings(memory_enabled=enabled))

    def _set_language(self, language: str, scope: LanguageScope) -> str:
        """Save the conversation language for the active personality or all of them, then reconnect."""
        if scope == "profile":
            profile = canonical_profile_name(config.REACHY_MINI_CUSTOM_PROFILE)
            changes = AppSettings(profile_languages={**config.PROFILE_LANGUAGES, profile: language})
        else:
            changes = AppSettings(language=language, profile_languages={})
        return self._apply_setting_with_restart(changes, "language_changed")

    def _persist_camera_enabled(self, enabled: bool) -> None:
        """Remember the camera switch across restarts."""
        self._save_settings(AppSettings(camera_enabled=enabled))

    def _persist_personality(self, profile: Optional[str], voice_override: Optional[str] = None) -> None:
        """Persist startup profile and voice in instance-local UI settings."""
        if LOCKED_PROFILE is not None:
            return
        selection = (profile or "").strip() or None
        normalized_voice_override = (voice_override or "").strip() or None
        set_custom_profile(selection)

        if not self._instance_path:
            return
        try:
            write_startup_settings(
                self._instance_path,
                profile=selection,
                voice=normalized_voice_override,
            )
            self._remove_persisted_env_values(LEGACY_STARTUP_ENV_NAMES)
            logger.info("Persisted startup personality settings to %s", Path(self._instance_path))
        except Exception as e:
            logger.warning("Failed to persist startup personality settings: %s", e)

    def _read_persisted_personality(self) -> Optional[str]:
        """Read the saved startup personality from instance-local UI settings."""
        return read_startup_settings(self._instance_path).profile

    async def apply_personality(self, profile: Optional[str]) -> str:
        """Apply a personality by updating config and restarting the active backend."""
        previous_profile = config.REACHY_MINI_CUSTOM_PROFILE
        set_custom_profile(profile)
        try:
            get_session_instructions()
            get_session_voice(default=get_default_voice())
            initialize_tools(force=True)
        except Exception:
            set_custom_profile(previous_profile)
            raise

        await self.request_backend_restart("personality_changed")
        return "人格已套用，正在重新啟動後端。"

    async def get_available_voices(self) -> list[str]:
        """Return voices for the selected provider."""
        if config.CONVERSATION_BACKEND == GEMINI_BACKEND:
            return list(GEMINI_AVAILABLE_VOICES)
        return get_available_voices()

    def get_current_voice(self) -> str:
        """Return the currently selected voice override or profile voice."""
        if config.CONVERSATION_BACKEND == GEMINI_BACKEND:
            return config.GEMINI_VOICE_OVERRIDE or get_session_voice(default=config.GEMINI_VOICE or "Kore")
        if self._voice_override:
            return self._voice_override
        try:
            return get_session_voice(default=get_default_voice())
        except Exception as exc:
            logger.warning("Failed to resolve the current profile voice: %s", exc)
            return get_default_voice()

    async def change_voice(self, voice: str) -> str:
        """Change the voice through the active handler without rebuilding the backend."""
        if config.CONVERSATION_BACKEND == GEMINI_BACKEND:
            if voice not in GEMINI_AVAILABLE_VOICES:
                raise ValueError("invalid_gemini_voice")
            self._save_settings(AppSettings(gemini_voice=voice))
            await self.request_backend_restart("voice_changed")
            return "聲音已儲存，正在開始新對話。"
        try:
            status = await self.handler.change_voice(voice)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Error changing voice to %r: %s", voice, e)
            return f"變更聲音失敗：{e}"

        try:
            current_voice = self.handler.get_current_voice()
            if isinstance(current_voice, str) and current_voice.strip():
                self._voice_override = current_voice
        except Exception as e:
            logger.debug("Could not sync LocalStream voice override after voice change: %s", e)
        if self._voice_override:
            self._persist_voice_override(self._voice_override)
        return status

    def _persist_voice_override(self, voice: str) -> None:
        """Persist the chosen voice as the startup voice, keeping the startup profile."""
        if not self._instance_path:
            return
        try:
            existing = read_startup_settings(self._instance_path)
            write_startup_settings(self._instance_path, profile=existing.profile, voice=voice)
        except Exception as e:
            logger.warning("Failed to persist startup voice: %s", e)

    def _init_settings_ui_if_needed(self) -> None:
        """Attach minimal settings UI to the settings app.

        Always mounts the UI when a settings_app is provided so that users
        see a confirmation message even if the API key is already configured.
        """
        if self._settings_initialized:
            return
        if self._settings_app is None:
            return
        settings_app = self._settings_app

        static_dir = Path(__file__).parent / "static"
        index_file = static_dir / "index.html"
        logger.info("Serving settings UI from %s", static_dir)

        # Framework pre-registers GET / and /static; strip them so our routes aren't shadowed.
        _detach_framework_root_routes(settings_app)

        if hasattr(settings_app, "mount"):
            try:
                settings_app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
            except Exception:
                logger.exception("Failed to mount settings UI static assets")
                raise

        def _status_payload() -> dict[str, object]:
            hf_session_url = get_hf_session_url()
            hf_ws_url = get_hf_direct_ws_url()
            hf_direct_host, hf_direct_port = parse_hf_direct_target(hf_ws_url)
            hf_connection_selection = get_hf_connection_selection()
            has_hf_connection = hf_connection_selection.has_target
            backend_connection = self._backend_connection_status()
            return {
                "backend": config.CONVERSATION_BACKEND,
                "gemini_model": config.GEMINI_MODEL,
                "gemini_voice": config.GEMINI_VOICE_OVERRIDE or get_session_voice(default=config.GEMINI_VOICE),
                "gemini_key_configured": bool(self._credentials.snapshot().secret)
                if self._credentials
                else bool(config.GEMINI_API_KEY),
                "gemini_credential": self._credential_status() if self._credentials else None,
                "has_key": has_hf_connection,
                "has_hf_session_url": bool(hf_session_url),
                "has_hf_ws_url": bool(hf_ws_url),
                "has_hf_connection": has_hf_connection,
                "hf_connection_mode": hf_connection_selection.mode,
                "hf_direct_host": hf_direct_host,
                "hf_direct_port": hf_direct_port,
                "can_proceed": (
                    bool(self._credentials.snapshot().secret) if self._credentials else bool(config.GEMINI_API_KEY)
                )
                if config.CONVERSATION_BACKEND == GEMINI_BACKEND
                else has_hf_connection,
                "can_proceed_with_hf": has_hf_connection,
                "requires_restart": not self._can_rebuild_handler(),
                # What the mobile client would otherwise need four more calls for.
                "personality": config.REACHY_MINI_CUSTOM_PROFILE,
                "voice": self.get_current_voice(),
                "language": get_session_language(),
                "memory_enabled": config.MEMORY_ENABLED,
                "local_vad_enabled": config.LOCAL_VAD_ENABLED,
                "local_barge_in_enabled": config.LOCAL_BARGE_IN_ENABLED,
                "vision_enabled": bool(self._tool_deps and self._tool_deps.camera_enabled),
                **backend_connection,
            }

        # GET / -> index.html
        @settings_app.get("/")
        def _root() -> FileResponse:
            return FileResponse(str(index_file))

        # GET /favicon.ico -> optional, avoid noisy 404s on some browsers
        @settings_app.get("/favicon.ico")
        def _favicon() -> Response:
            return Response(status_code=204)

        # ── JSON-RPC control surface (/rpc) ──────────────────────────────
        # The single wire format both the local browser UI and remote WebRTC
        # clients use (the daemon relays it over the DataChannel). Notifications
        # (conversation.turn/phase/transcript/latency/activity) are pushed from activity.
        rpc = JsonRpcServer()

        # SDK isn't marked py.typed, so mypy sees rpc.method as untyped; safe here.
        @rpc.method("conversation.status")  # type: ignore[untyped-decorator]
        def _rpc_status(_params: dict[str, object]) -> dict[str, object]:
            return _status_payload()

        rpc.register("status.get", _rpc_status)

        @rpc.method("conversation.say")  # type: ignore[untyped-decorator]
        async def _rpc_say(params: dict[str, object]) -> dict[str, object]:
            text = str(params.get("text", "")).strip()
            if not text:
                raise JsonRpcError("say requires 'text'", reason="invalid_params", code=-32602)
            if not self.handler._is_connected():
                raise JsonRpcError("no active session", reason="not_running")
            if config.CONVERSATION_BACKEND == GEMINI_BACKEND:
                self._pending_say = text
                await self.request_backend_restart("injected_speech")
            else:
                await self.handler.interrupt()
                await self.handler.say(text)
            return {"ok": True}

        @rpc.method("conversation.interrupt")  # type: ignore[untyped-decorator]
        async def _rpc_interrupt(_params: dict[str, object]) -> dict[str, object]:
            if not self.handler._is_connected():
                raise JsonRpcError("no active session", reason="not_running")
            await self.handler.interrupt()
            self._last_turn_state = "listening"
            rpc.broadcast_threadsafe("conversation.turn", {"state": "listening", "reason": "interrupted"})
            return {"ok": True}

        @rpc.method("conversation.history")  # type: ignore[untyped-decorator]
        def _rpc_history(_params: dict[str, object]) -> dict[str, object]:
            return {"events": list(self._conversation_history)}

        @rpc.method("conversation.mic")  # type: ignore[untyped-decorator]
        def _rpc_mic(params: dict[str, object]) -> dict[str, object]:
            if "muted" in params:
                muted = bool(params["muted"])
                if muted != self._mic_muted:
                    self._microphone_epoch += 1
                    self._mic_muted = muted
                logger.info("Microphone %s via /rpc", "muted" if self._mic_muted else "unmuted")
            return {"muted": self._mic_muted}

        @rpc.method("backend.config")  # type: ignore[untyped-decorator]
        def _rpc_backend_config(params: dict[str, object]) -> dict[str, object]:
            allowed = {"backend", "hf_mode", "hf_host", "hf_port", "gemini_model", "gemini_voice"}
            if set(params) - allowed:
                raise JsonRpcError("unknown connection parameter", reason="invalid_params", code=-32602)
            legacy_hf = bool(set(params) & {"hf_mode", "hf_host", "hf_port"})
            backend = normalize_conversation_backend(
                params.get("backend", HF_BACKEND if legacy_hf else config.CONVERSATION_BACKEND)
            )
            if backend is None:
                raise JsonRpcError("invalid provider", reason="invalid_backend", code=-32602)
            model, voice = params.get("gemini_model"), params.get("gemini_voice")
            if model is not None and (
                not isinstance(model, str) or not re.fullmatch(r"(?:models/)?[a-zA-Z0-9._-]+", model)
            ):
                raise JsonRpcError("invalid Gemini model", reason="invalid_gemini_model", code=-32602)
            if voice is not None and (not isinstance(voice, str) or voice not in GEMINI_AVAILABLE_VOICES):
                raise JsonRpcError("select a Gemini voice", reason="invalid_gemini_voice", code=-32602)
            if self._credentials is not None:
                self._credentials.invalidate()
                validation_task = self._credential_validation_task
                if validation_task is not None and not validation_task.done():
                    validation_task.get_loop().call_soon_threadsafe(validation_task.cancel)
                if backend == GEMINI_BACKEND and self._credentials.metadata.manual_reconnect_required:
                    try:
                        self._credentials.set_manual_reconnect(False)
                    except CredentialError as error:
                        raise JsonRpcError("credential recovery required", reason=error.reason) from None
                self._credential_hold = False
            if backend == GEMINI_BACKEND or not legacy_hf:
                self._save_settings(
                    AppSettings(
                        conversation_backend=backend,
                        gemini_model=model if isinstance(model, str) else None,
                        gemini_voice=voice if isinstance(voice, str) else None,
                    )
                )
                self._mark_restart_requested("backend_config_changed")
                return {"ok": True, "message": "選擇已儲存，正在開始新對話。", **_status_payload()}
            hf_selection = get_hf_connection_selection()
            hf_mode = str(params.get("hf_mode") or hf_selection.mode).strip().lower()
            if hf_mode == HF_LOCAL_CONNECTION_MODE:
                existing_host, existing_port = parse_hf_direct_target(hf_selection.direct_ws_url)
                host = str(params.get("hf_host") or "").strip() or existing_host or ""
                if not host:
                    raise JsonRpcError("Hugging Face host required", reason="empty_hf_host", code=-32602)
                if "://" in host or "/" in host or "?" in host or "#" in host:
                    raise JsonRpcError("invalid Hugging Face host", reason="invalid_hf_host", code=-32602)
                raw_port = params.get("hf_port")
                try:
                    port = int(raw_port) if isinstance(raw_port, (int, float, str)) else (existing_port or 8765)
                except (ValueError, OverflowError):
                    raise JsonRpcError("invalid Hugging Face port", reason="invalid_hf_port", code=-32602) from None
                if port < 1 or port > 65535:
                    raise JsonRpcError("invalid Hugging Face port", reason="invalid_hf_port", code=-32602)
                self._persist_hf_direct_connection(host, port)
            elif hf_mode == HF_DEPLOYED_CONNECTION_MODE:
                if not bool(get_hf_session_url()):
                    raise JsonRpcError(
                        "missing Hugging Face session url", reason="missing_hf_session_url", code=-32602
                    )
                self._persist_hf_allocator_connection()
            else:
                raise JsonRpcError("invalid Hugging Face mode", reason="invalid_hf_mode", code=-32602)

            self._save_settings(
                AppSettings(
                    conversation_backend=backend,
                    gemini_model=model if isinstance(model, str) else None,
                    gemini_voice=voice if isinstance(voice, str) else None,
                )
            )
            if self._can_rebuild_handler():
                self._mark_restart_requested("backend_config_changed")
                message = "連線已儲存，正在重新連接後端。"
            else:
                message = "連線已儲存，請從桌面應用程式重新啟動 Reachy Mini Conversation 以套用。"
            return {"ok": True, "message": message, **_status_payload()}

        def _rpc_backend_retry(params: dict[str, object]) -> dict[str, object]:
            if params:
                raise JsonRpcError("Retry takes no parameters", reason="invalid_params", code=-32602)
            if self._credentials is not None and config.CONVERSATION_BACKEND == GEMINI_BACKEND:
                if self._credentials.validation == "validating" or self._credentials.apply in ("saving", "clearing"):
                    raise JsonRpcError("credential operation in progress", reason="storage_busy")
                try:
                    self._credentials.set_manual_reconnect(False)
                except CredentialError as error:
                    raise JsonRpcError("credential recovery required", reason=error.reason) from None
                self._credential_hold = False
            if self._backend_connected() or self._backend_connection_state == "connecting":
                return {"ok": True, "message": "連線已啟用或正在連線。", **_status_payload()}
            loop = self._asyncio_loop
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self._retry_requested.set)
            else:
                self._retry_requested.set()
            return {"ok": True, "message": "已排定重試。", **_status_payload()}

        rpc.register("backend.retry", _rpc_backend_retry)

        def _rpc_speech_config(params: dict[str, object]) -> dict[str, object]:
            names = ("local_vad_enabled", "local_barge_in_enabled")
            for name in names:
                if name in params and not isinstance(params[name], bool):
                    raise JsonRpcError(f"{name} must be a boolean", reason="invalid_params", code=-32602)
            enabled = params.get("local_vad_enabled")
            barge_in = params.get("local_barge_in_enabled")
            message = ""
            if (isinstance(enabled, bool) and enabled != config.LOCAL_VAD_ENABLED) or (
                isinstance(barge_in, bool) and barge_in != config.LOCAL_BARGE_IN_ENABLED
            ):
                message = self._apply_setting_with_restart(
                    AppSettings(
                        local_vad_enabled=enabled if isinstance(enabled, bool) else None,
                        local_barge_in_enabled=barge_in if isinstance(barge_in, bool) else None,
                    ),
                    "speech_settings_changed",
                )
            return {
                "local_vad_enabled": config.LOCAL_VAD_ENABLED,
                "local_barge_in_enabled": config.LOCAL_BARGE_IN_ENABLED,
                "message": message,
                "requires_restart": not self._can_rebuild_handler(),
            }

        rpc.register("speech.config", _rpc_speech_config)
        rpc.mount(settings_app)
        self._rpc = rpc

        try:
            personality_ops = build_personality_ops(
                self.handler,
                lambda: self._asyncio_loop,
                persist_personality=self._persist_personality,
                get_persisted_personality=self._read_persisted_personality,
                apply_personality=self.apply_personality,
                get_voices=self.get_available_voices,
                get_current_voice=self.get_current_voice,
                change_voice=self.change_voice,
            )
            # personalities.* / voices.* over JSON-RPC — the local UI and remote
            # clients drive personalities the same way, one control surface.
            register_personality_methods(rpc, personality_ops)
        except Exception:
            logger.exception("Failed to register personality methods; the personality UI will be unavailable")

        try:
            register_tool_space_methods(
                rpc,
                lambda: self._asyncio_loop,
                self.request_backend_restart,
                instance_path=self._instance_path,
            )
        except Exception:
            logger.exception("Failed to register Tool Space methods; remote tool settings will be unavailable")

        try:
            register_profile_tool_methods(
                rpc,
                lambda: self._asyncio_loop,
                self.request_backend_restart,
                instance_path=self._instance_path,
            )
        except Exception:
            logger.exception("Failed to register profile tool methods; personality tool settings will be unavailable")

        try:
            # memory.* / language.* / vision.* — the settings a remote client
            # (the mobile app) shows next to the personality controls.
            register_memory_methods(
                rpc,
                instance_path=self._instance_path,
                set_enabled=self._set_memory_enabled,
                refresh_instructions=self._refresh_instructions,
            )
        except Exception:
            logger.exception("Failed to register memory methods; memory settings will be unavailable")

        try:
            register_language_methods(rpc, set_language=self._set_language)
        except Exception:
            logger.exception("Failed to register language methods; the language setting will be unavailable")

        if self._tool_deps is not None:
            try:
                register_vision_methods(
                    rpc,
                    self._tool_deps,
                    self._persist_camera_enabled,
                    forced_off=self._camera_forced_off,
                )
            except Exception:
                logger.exception("Failed to register vision methods; the camera switch will be unavailable")

        settings_app.add_api_route(
            "/api/gemini-credential", self._credential_endpoint, methods=["GET", "POST", "DELETE"]
        )
        settings_app.add_api_route("/settings/gemini-key", self._credential_page, methods=["GET"])
        self._settings_initialized = True

    @staticmethod
    def _check_credential_request(request: Request, *, document: bool = False) -> None:
        client = request.client
        try:
            local = client is not None and ipaddress.ip_address(client.host).is_loopback
            host = urlsplit("http://" + request.headers.get("host", ""))
            server: object = request.scope.get("server")
            port = server[1] if isinstance(server, (tuple, list)) and len(server) == 2 else None
            valid_host = (
                host.hostname in ("localhost", "127.0.0.1", "::1")
                and host.username is None
                and host.password is None
                and not host.path
                and not host.query
                and not host.fragment
                and (host.port or (443 if request.url.scheme == "https" else 80)) == port
            )
        except ValueError:
            local, valid_host = False, False
        if (
            not local
            or not valid_host
            or any(name == "forwarded" or name.startswith("x-forwarded-") for name in request.headers)
        ):
            raise CredentialError("local_access_required")
        if document:
            if request.headers.get("sec-fetch-dest", "document") != "document":
                raise CredentialError("request_not_allowed")
            return
        origin = request.headers.get("origin")
        expected_origin = str(request.base_url).rstrip("/")
        if request.headers.get("sec-fetch-site") != "same-origin" or (origin and origin != expected_origin):
            raise CredentialError("request_not_allowed")
        if request.method == "GET":
            if request.headers.get("x-credential-request") != "1":
                raise CredentialError("request_not_allowed")
        elif origin != expected_origin or request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise CredentialError("request_not_allowed")

    def _credential_status(self) -> dict[str, object]:
        if self._credentials is None:
            return {"configured": False, "source": "none", "storage": "unavailable", "reason": "storage_unavailable"}
        return {
            **self._credentials.status(),
            "backend": config.CONVERSATION_BACKEND,
            "connection": self._backend_connection_status()["backend_connection_state"],
            "model": config.GEMINI_MODEL,
            "voice": config.GEMINI_VOICE_OVERRIDE or config.GEMINI_VOICE,
        }

    def _credential_page(self, request: Request) -> Response:
        try:
            self._check_credential_request(request, document=True)
        except CredentialError as error:
            return JSONResponse({"reason": error.reason}, status_code=403, headers={"Cache-Control": "no-store"})
        return FileResponse(
            Path(__file__).parent / "templates" / "gemini-key.html",
            headers={
                "Cache-Control": "no-store",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
                "Referrer-Policy": "no-referrer",
            },
        )

    async def _credential_endpoint(self, request: Request) -> Response:
        revision: int | None = None
        try:
            self._check_credential_request(request)
            if self._credentials is None:
                raise CredentialError("storage_unavailable")
            if request.method == "GET":
                if time.monotonic() >= self._credential_csrf_expires:
                    self._credential_csrf = secrets.token_urlsafe(32)
                    self._credential_csrf_expires = time.monotonic() + 600
                return JSONResponse(
                    {**self._credential_status(), "csrf_token": self._credential_csrf},
                    headers={"Cache-Control": "no-store"},
                )
            token = request.headers.get("x-credential-csrf", "")
            if time.monotonic() >= self._credential_csrf_expires or not secrets.compare_digest(
                token, self._credential_csrf
            ):
                raise CredentialError("request_not_allowed")
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 16 * 1024:
                    raise CredentialError("invalid_input")
                body.extend(chunk)
            try:
                payload: object = json.loads(body)
            except (ValueError, UnicodeError):
                raise CredentialError("invalid_input") from None
            if not isinstance(payload, dict):
                raise CredentialError("invalid_input")
            expected = payload.get("expected_revision")
            if type(expected) is not int or expected < 0:
                raise CredentialError("invalid_input")
            candidate = payload.get("candidate")
            clearing = request.method == "DELETE"
            if clearing:
                if set(payload) != {"expected_revision", "confirm"} or payload.get("confirm") is not True:
                    raise CredentialError("invalid_input")
            elif (
                set(payload) != {"expected_revision", "candidate"}
                or not isinstance(candidate, str)
                or not candidate.strip()
            ):
                raise CredentialError("invalid_input")
            revision = self._credentials.begin(expected, clear=clearing)
            if config.CONVERSATION_BACKEND == GEMINI_BACKEND:
                self._credential_hold = True
            operation = self._change_credential(
                candidate.strip() if isinstance(candidate, str) else "", revision, clearing
            )
            loop = self._asyncio_loop
            if loop is not None and loop.is_running() and loop is not asyncio.get_running_loop():
                await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(operation, loop))
            else:
                await operation
            return JSONResponse(self._credential_status(), headers={"Cache-Control": "no-store"})
        except (CredentialError, GeminiConnectionError) as error:
            reason = error.reason
            if revision is not None and self._credentials is not None:
                self._credentials.failure(reason, revision)
            code = {
                "invalid_input": 400,
                "local_access_required": 403,
                "request_not_allowed": 403,
                "revision_conflict": 409,
                "superseded": 409,
                "storage_busy": 409,
                "authentication_failed": 422,
                "model_not_available": 422,
                "invalid_gemini_model": 422,
                "invalid_gemini_voice": 422,
                "quota_exceeded": 429,
                "validation_timeout": 504,
            }.get(reason, 503)
            logger.warning("Credential HTTP operation rejected: %s", reason)
            return JSONResponse(
                {**self._credential_status(), "reason": reason},
                status_code=code,
                headers={"Cache-Control": "no-store"},
            )

    async def _change_credential(self, candidate: str, revision: int, clearing: bool) -> None:
        credentials = self._credentials
        if credentials is None:
            raise CredentialError("storage_unavailable")
        model, voice = config.GEMINI_MODEL, config.GEMINI_VOICE_OVERRIDE or config.GEMINI_VOICE
        provider = config.CONVERSATION_BACKEND
        if revision != credentials.revision:
            raise CredentialError("superseded")
        if clearing:
            validation_task = self._credential_validation_task
            if validation_task is not None and not validation_task.done():
                validation_task.get_loop().call_soon_threadsafe(validation_task.cancel)
        if provider == GEMINI_BACKEND:
            await self._stop_gemini_for_credentials()
            if revision != credentials.revision:
                raise CredentialError("superseded")
            await asyncio.to_thread(credentials.set_manual_reconnect, True, revision)
        try:
            if revision != credentials.revision:
                raise CredentialError("superseded")
            if clearing:
                await asyncio.to_thread(credentials.clear, revision)
                return
            validation_task = asyncio.create_task(validate_gemini_candidate(candidate, model, voice))
            self._credential_validation_task = validation_task
            await validation_task
            if (
                revision != credentials.revision
                or provider != config.CONVERSATION_BACKEND
                or model != config.GEMINI_MODEL
                or voice != (config.GEMINI_VOICE_OVERRIDE or config.GEMINI_VOICE)
            ):
                raise CredentialError("superseded")
            await asyncio.to_thread(credentials.save, candidate, revision)
            if revision != credentials.revision:
                raise CredentialError("superseded")
            if provider == GEMINI_BACKEND and config.CONVERSATION_BACKEND == GEMINI_BACKEND:
                await asyncio.to_thread(credentials.set_manual_reconnect, False, revision)
                if revision == credentials.revision:
                    self._credential_hold = False
                    await self.request_backend_restart("credential_applied")
        except asyncio.CancelledError:
            if revision != credentials.revision:
                raise CredentialError("superseded") from None
            credentials.invalidate()
            raise

    async def _stop_gemini_for_credentials(self) -> None:
        if config.CONVERSATION_BACKEND != GEMINI_BACKEND:
            return
        self._credential_hold = True
        self._restart_requested.set()
        async with self._transition_lock:
            self._pending_say = None
            if self._session_task is not None:
                self._session_task.cancel()
            self.session_state.fresh(GEMINI_BACKEND, "")
            if self._tool_deps is not None:
                self._tool_deps.movement_manager.clear_move_queue()
            await self._shutdown_active_handler()
        self._set_backend_connection_state("waiting_for_config", "manual_reconnect_required")

    def _configuration_ready(self) -> bool:
        if config.CONVERSATION_BACKEND == GEMINI_BACKEND:
            if self._credentials is not None:
                return (
                    bool(self._credentials.snapshot().secret)
                    and not self._credentials.metadata.manual_reconnect_required
                    and not self._credential_hold
                )
            return bool(config.GEMINI_API_KEY)
        return has_hf_realtime_target()

    async def _run_handler_startup_loop(self) -> None:
        """Own the sole recovery schedule for the explicitly selected provider."""
        replace = False
        while not self._stop_event.is_set():
            recoverable = True
            try:
                if self._restart_requested.is_set() or replace:
                    await self._shutdown_active_handler()
                    if self.session_state.provider != config.CONVERSATION_BACKEND:
                        if self.session_state.mark_uncertain_actions():
                            self._dispatch_activity("uncertain_action")
                        self.session_state.fresh(config.CONVERSATION_BACKEND, "")
                        self._dispatch_activity("fresh_context")
                    if self._restart_requested.is_set() and not self._can_rebuild_handler():
                        self._restart_requested.clear()
                        self._set_backend_connection_state("restart_required")
                        await self._sleep_or_restart_requested(0.5)
                        continue
                    self._restart_requested.clear()
                    if self._can_rebuild_handler():
                        self._build_handler_for_current_backend()
                    replace = False
                if not self._configuration_ready():
                    reason = (
                        "missing_gemini_key"
                        if config.CONVERSATION_BACKEND == GEMINI_BACKEND
                        else "Hugging Face target is not configured."
                    )
                    self._set_backend_connection_state("waiting_for_config", reason)
                    await self._sleep_or_restart_requested(0.5)
                    continue
                self.session_state.begin_connection()
                revision = hashlib.sha256(
                    json.dumps(
                        {
                            "provider": config.CONVERSATION_BACKEND,
                            "model": config.GEMINI_MODEL,
                            "voice": self.get_current_voice(),
                            "instructions": get_session_instructions(self._instance_path),
                            "tools": get_tool_specs(),
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                if self.session_state.revision and self.session_state.revision != revision:
                    if self.session_state.mark_uncertain_actions():
                        self._dispatch_activity("uncertain_action")
                    self.session_state.fresh(config.CONVERSATION_BACKEND, revision)
                    self._dispatch_activity("fresh_context")
                self.session_state.revision = revision
                if isinstance(self.handler, RealtimeConversationHandler):
                    self.handler._generation = self.session_state.generation
                    self.handler._closed = False
                self._retry_delay_seconds = None
                self._set_backend_connection_state("connecting")
                self._session_task = asyncio.create_task(self.handler.start_up())
                deadline = time.monotonic() + SETUP_TIMEOUT_S
                acknowledged = False
                while not self._session_task.done():
                    if self._restart_requested.is_set() or self._stop_event.is_set():
                        self.session_state.begin_connection()
                        self._session_task.cancel()
                        break
                    if not acknowledged and self._backend_connected():
                        acknowledged = True
                        if config.CONVERSATION_BACKEND == HF_BACKEND:
                            self.session_state.context_state = "new"
                            self._dispatch_activity("fresh_context")
                    if (
                        acknowledged
                        and isinstance(self.handler, RealtimeConversationHandler)
                        and not self.handler._owns_connection()
                    ):
                        self._session_task.cancel()
                        raise GeminiConnectionError(self.handler.connection_error_reason or "connection_lost")
                    if acknowledged and self._pending_say is not None:
                        text, self._pending_say = self._pending_say, None
                        await self.handler.say(text)
                    if not acknowledged and time.monotonic() >= deadline:
                        self.session_state.begin_connection()
                        self._session_task.cancel()
                        raise GeminiConnectionError("setup_timeout")
                    await asyncio.wait({self._session_task}, timeout=0.05)
                if self._session_task.done():
                    await self._session_task
                else:
                    self._session_task.add_done_callback(self._consume_retired_task)
                self._set_backend_connection_state("disconnected", "connection_lost")
            except asyncio.CancelledError:
                owner_task = asyncio.current_task()
                if owner_task is not None and owner_task.cancelling():
                    raise
                self._restart_requested.set()
            except Exception as error:
                if isinstance(error, GeminiConnectionError):
                    recoverable = error.recoverable
                elif isinstance(error, (httpx.HTTPStatusError, APIStatusError, InvalidStatus)):
                    code = error.response.status_code
                    remote_body = error.response.body if isinstance(error, InvalidStatus) else error.response.content
                    remote_message = (
                        bytes(remote_body).decode("utf-8", errors="replace").lower() if remote_body else ""
                    )
                    if code in (400, 401, 403, 404):
                        recoverable = False
                        error = GeminiConnectionError(
                            {
                                400: "invalid_params",
                                401: "authentication_failed",
                                403: "access_unavailable",
                                404: "access_unavailable",
                            }[code],
                            recoverable=False,
                        )
                    elif code == 429 and any(
                        word in remote_message
                        for word in ("insufficient_quota", "billing", "daily", "quota exhausted")
                    ):
                        recoverable = False
                        error = GeminiConnectionError("quota_exceeded", recoverable=False)
                elif isinstance(error, ValueError):
                    recoverable = False
                self._set_backend_connection_state("disconnected" if recoverable else "waiting_for_config", error)
                logger.warning("Backend attempt ended: %s", self._backend_error)
            finally:
                if self._session_task is not None and not self._session_task.done():
                    self.session_state.begin_connection()
                    self._session_task.cancel()
                    self._session_task.add_done_callback(self._consume_retired_task)
                self._session_task = None
            if self._stop_event.is_set():
                return
            await self._shutdown_active_handler()
            self.session_state.context_state = "unavailable"
            replace = True
            if self._restart_requested.is_set():
                continue
            if recoverable:
                self._retry_attempt += 1
                self._retry_delay_seconds = min(30.0, 2.0 ** min(self._retry_attempt - 1, 5))
                await self._sleep_or_restart_requested(self._retry_delay_seconds)
            else:
                self._retry_delay_seconds = None
                await self._sleep_or_restart_requested(None)

    def launch(self) -> None:
        """Start the recorder/player and run the async processing loops.

        If the selected backend is missing its required key, expose a tiny
        settings UI via the Reachy Mini settings server to collect it before
        starting streams.
        """
        self._stop_event.clear()

        # Try to load an existing instance .env first (covers subsequent runs)
        if self._instance_path:
            try:
                from dotenv import load_dotenv

                env_path = Path(self._instance_path) / ".env"
                if env_path.exists():
                    load_dotenv(dotenv_path=str(env_path), override=True)
                    refresh_runtime_config_from_env()
            except Exception:
                pass  # Instance .env loading is optional; continue with defaults
            load_settings_into_runtime(self._instance_path)

        # Always expose settings UI if a settings app is available
        # (do this AFTER loading the instance .env so status endpoint sees the right value)
        self._init_settings_ui_if_needed()

        # If the Hugging Face target is still missing -> wait until provided via the settings UI
        if not self._configuration_ready():
            self._set_backend_connection_state("waiting_for_config", f"{HF_REALTIME_WS_URL_ENV} is not configured.")
            if self._settings_app is None:
                logger.error(
                    "%s not found. Set it in the app .env before starting the Hugging Face backend.",
                    HF_REALTIME_WS_URL_ENV,
                )
                return
            logger.warning("%s not found. Open the app settings page to configure it.", HF_REALTIME_WS_URL_ENV)
            # Poll until a target becomes available (set via the settings UI)
            try:
                while not self._stop_event.is_set() and not self._configuration_ready():
                    time.sleep(0.2)
            except KeyboardInterrupt:
                logger.info("Interrupted while waiting for Hugging Face configuration.")
                return
            if self._stop_event.is_set():
                return
            self._set_backend_connection_state("not_started")

        # Start media after key is set/available
        self._audio_warming_up = True
        self._robot.media.start_recording()
        self._robot.media.start_playing()

        async def runner() -> None:
            # Capture loop for cross-thread personality actions
            loop = asyncio.get_running_loop()
            self._asyncio_loop = loop  # type: ignore[assignment]
            # Connect the backend first so it overlaps the warmup and audio config below.
            handler_task = asyncio.create_task(self._run_handler_startup_loop(), name="realtime-handler")
            self._tasks = [
                handler_task,
                asyncio.create_task(self.record_loop(), name="stream-record-loop"),
            ]
            try:
                await asyncio.gather(
                    asyncio.sleep(1),  # give the pipelines time to start
                    asyncio.to_thread(apply_audio_startup_config, self._robot, logger=logger),
                )
                if self._stop_event.is_set():
                    return
                self._audio_warming_up = False
                self._tasks.append(asyncio.create_task(self.play_loop(), name="stream-play-loop"))
                await asyncio.gather(*self._tasks)
            except asyncio.CancelledError:
                logger.info("Tasks cancelled during shutdown")
            finally:
                # Ensure handler connection is closed
                await self._shutdown_active_handler()

        # Proactor TLS shutdown can raise WinError 10022 after an otherwise clean close.
        loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
        asyncio.run(runner(), loop_factory=loop_factory)

    def close(self) -> None:
        """Stop the stream and underlying media pipelines.

        This method:
        - Stops audio recording and playback first
        - Sets the stop event to signal async loops to terminate
        - Cancels all pending async tasks (openai-handler, record-loop, play-loop)
        """
        logger.info("Stopping LocalStream...")

        # Stop media pipelines FIRST before cancelling async tasks
        # This ensures clean shutdown before PortAudio cleanup
        try:
            self._robot.media.stop_recording()
        except Exception as e:
            logger.debug(f"Error stopping recording (may already be stopped): {e}")

        try:
            self._robot.media.stop_playing()
        except Exception as e:
            logger.debug(f"Error stopping playback (may already be stopped): {e}")

        # close() runs on watcher threads, loop-owned state must change on the loop.
        loop = self._asyncio_loop
        if loop is None or not loop.is_running():
            self._stop_event.set()
            return
        loop.call_soon_threadsafe(self._stop_event.set)
        for task in self._tasks:
            if not task.done():
                loop.call_soon_threadsafe(task.cancel)

    async def clear_audio_queue(self, expected_handler: ConversationHandler | None = None) -> None:
        """Invalidate pending chunks and flush SDK playback without blocking microphone capture."""
        async with self._playback_flush_lock:
            if expected_handler is not None and self.handler is not expected_handler:
                return
            logger.info("User intervention: flushing player queue")
            handler = self.handler
            handler.playback_epoch += 1
            if isinstance(handler.playback_epoch, int):
                self.session_state.response_epoch = handler.playback_epoch
            handler.playback_until = 0.0
            self._playback_clock = 0.0
            handler.playback_pending_frames = 0
            if self._playback_resampler is not None:
                self._playback_resampler.reset()
            handler.playback_ready.clear()
            self._drain_output_queue()
            audio = self._robot.media.audio
            try:
                if audio is not None:
                    flush_task = asyncio.create_task(asyncio.to_thread(audio.clear_player))
                    try:
                        finished, _pending = await asyncio.wait({flush_task}, timeout=CLOSE_TIMEOUT_S)
                        if finished:
                            await flush_task
                        else:
                            logger.warning("Player flush exceeded five seconds")
                    finally:
                        if not flush_task.done():
                            flush_task.cancel()
                            flush_task.add_done_callback(self._consume_retired_task)
            except (OSError, RuntimeError) as exc:
                logger.warning("Failed to clear player queue: %s", exc)
            finally:
                handler.playback_ready.set()

    def _drain_output_queue(self) -> None:
        """Remove pending audio in place while retaining text and metadata."""
        queue = getattr(self.handler, "output_queue", None)
        if queue is None:
            return
        retained_outputs: list[AdditionalOutputs] = []
        while not queue.empty():
            try:
                output = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if isinstance(output, AdditionalOutputs):
                retained_outputs.append(output)
            else:
                self.handler.playback_frame_epochs.pop(id(output[1]), None)
        for output in retained_outputs:
            queue.put_nowait(output)

    async def record_loop(self) -> None:
        """Read mic frames from the recorder and forward them to the handler."""
        input_sample_rate = self._robot.media.get_input_audio_samplerate()
        logger.debug(f"Audio recording started at {input_sample_rate} Hz")

        loop = asyncio.get_running_loop()
        frames: asyncio.Queue[tuple[int, int, AudioFrame]] = asyncio.Queue(maxsize=1)
        stop_reading = threading.Event()
        max_pending_samples = max(1, int(input_sample_rate * MICROPHONE_BUFFER_SECONDS))
        overflow_reported = False

        def deliver(generation: int, microphone_epoch: int, frame: AudioFrame) -> None:
            nonlocal overflow_reported
            if (
                self._stop_event.is_set()
                or self._mic_muted
                or generation != self.session_state.generation
                or microphone_epoch != self._microphone_epoch
            ):
                return
            if frames.full():
                pending_generation, pending_epoch, pending_frame = frames.get_nowait()
                if (
                    pending_generation == generation
                    and pending_epoch == microphone_epoch
                    and pending_frame[0] == frame[0]
                ):
                    # Preserve contiguous speech when SDK chunks arrive faster than sends complete.
                    samples = np.concatenate((pending_frame[1], frame[1]), axis=0)
                    if samples.shape[0] > max_pending_samples:
                        samples = samples[-max_pending_samples:]
                        if not overflow_reported:
                            logger.warning("Microphone input backlog exceeded 250 ms; dropping oldest pending samples")
                            overflow_reported = True
                    frame = (frame[0], samples)
            frames.put_nowait((generation, microphone_epoch, frame))

        def read_microphone() -> None:
            # The SDK read blocks up to 20 ms: one reader thread costs less than a thread hop per frame.
            while not stop_reading.is_set() and not self._stop_event.is_set():
                warming_up = self._audio_warming_up  # a read spanning the end of warmup still holds warmup audio
                generation = self.session_state.generation
                microphone_epoch = self._microphone_epoch
                connected = self._backend_connected()
                audio_frame = self._robot.media.get_audio_sample()
                if (
                    audio_frame is not None
                    and not warming_up
                    and connected
                    and generation == self.session_state.generation
                ):
                    loop.call_soon_threadsafe(deliver, generation, microphone_epoch, (input_sample_rate, audio_frame))

        reader = threading.Thread(target=read_microphone, name="microphone-reader", daemon=True)
        reader.start()
        try:
            while not self._stop_event.is_set():
                try:
                    generation, microphone_epoch, frame = await asyncio.wait_for(frames.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                overflow_reported = False
                if (
                    not self._mic_muted
                    and generation == self.session_state.generation
                    and microphone_epoch == self._microphone_epoch
                ):
                    await self.handler.receive(frame)
                    self._emit_level("user", frame[1])
        finally:
            stop_reading.set()
            await asyncio.to_thread(reader.join)

    async def play_loop(self) -> None:
        """Fetch outputs from the handler: log text and play audio frames."""
        while not self._stop_event.is_set():
            handler = self.handler
            generation = self.session_state.generation
            playback_epoch = handler.playback_epoch
            try:
                handler_output = await asyncio.wait_for(handler.emit(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if handler is not self.handler or generation != self.session_state.generation:
                continue
            if isinstance(handler, RealtimeConversationHandler) and not handler._owns_connection():
                continue

            if isinstance(handler_output, AdditionalOutputs):
                for msg in handler_output.args:
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        logger.info(
                            "role=%s content=%s",
                            msg.get("role"),
                            content if len(content) < 500 else content[:500] + "…",
                        )

            elif isinstance(handler_output, tuple):
                sample_rate, audio_data = handler_output
                playback_epoch = handler.playback_frame_epochs.pop(id(audio_data), playback_epoch)
                if handler is not self.handler or playback_epoch != handler.playback_epoch:
                    continue
                if handler.paced_playback is True:
                    handler.playback_pending_frames = max(0, handler.playback_pending_frames - 1)

                # Skip empty audio frames
                if audio_data.size == 0:
                    continue

                output_rate = self._robot.media.get_output_audio_samplerate()
                if isinstance(output_rate, int) and output_rate > 0 and sample_rate != output_rate:
                    rates = (sample_rate, output_rate, playback_epoch)
                    if self._playback_rates != rates:
                        self._playback_rates = rates
                        self._playback_resampler = AudioResampler(sample_rate, output_rate)
                    if self._playback_resampler is not None:
                        audio_data = self._playback_resampler.process(audio_data.reshape(-1))
                        sample_rate = output_rate

                # Reshape if needed
                if audio_data.ndim == 2:
                    # channels-last convention
                    if audio_data.shape[1] > audio_data.shape[0]:
                        audio_data = audio_data.T
                    # Multiple channels -> Mono channel
                    if audio_data.shape[1] > 1:
                        audio_data = audio_data[:, 0]

                # Cast if needed
                audio_frame = audio_to_float32(audio_data)

                if handler.paced_playback is True:
                    chunk_samples = max(1, sample_rate // 50)
                    for offset in range(0, audio_frame.size, chunk_samples):
                        # One schedule across frames: the SDK lays follow-up buffers back to back and
                        # only re-anchors after a 200 ms gap, so restarting per frame accumulated lateness.
                        now = time.monotonic()
                        if now > self._playback_clock + 0.2:
                            self._playback_clock = now
                        await asyncio.sleep(max(0.0, self._playback_clock - PLAYBACK_LEAD_SECONDS - now))
                        await handler.playback_ready.wait()
                        if (
                            self._stop_event.is_set()
                            or handler is not self.handler
                            or playback_epoch != handler.playback_epoch
                        ):
                            break
                        chunk = audio_frame[offset : offset + chunk_samples] * handler.playback_gain
                        self._robot.media.push_audio_sample(chunk)
                        self._emit_level("assistant", chunk)
                        self._playback_clock += chunk.size / sample_rate
                        handler.playback_until = self._playback_clock + 0.1
                else:
                    # A flush in progress would drop or misplace this push.
                    await handler.playback_ready.wait()
                    if handler is not self.handler or playback_epoch != handler.playback_epoch:
                        continue
                    self._robot.media.push_audio_sample(audio_frame)
                    self._emit_level("assistant", audio_frame)

            else:
                logger.debug("Ignoring output type=%s", type(handler_output).__name__)

            await asyncio.sleep(0)  # yield to event loop
