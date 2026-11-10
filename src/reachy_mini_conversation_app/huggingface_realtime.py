import json
import math
import time
import uuid
import base64
import asyncio
import logging
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Final, Tuple, Optional
from collections import deque
from dataclasses import field, dataclass
from collections.abc import Awaitable

import httpx
import numpy as np
from openai import AsyncOpenAI
from pydantic import Field, BaseModel
from numpy.typing import NDArray
from huggingface_hub import get_token
from typing_extensions import Literal, TypedDict
from openai.types.realtime import (
    AudioTranscriptionParam,
    RealtimeAudioConfigParam,
    RealtimeToolsConfigParam,
    RealtimeFunctionToolParam,
    RealtimeAudioConfigInputParam,
    RealtimeAudioConfigOutputParam,
    RealtimeSessionCreateRequestParam,
)
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from openai.types.realtime.realtime_audio_input_turn_detection_param import ServerVad

from reachy_mini_conversation_app.tools import core_tools
from reachy_mini_conversation_app.config import (
    HF_LOCAL_CONNECTION_MODE,
    config,
    get_default_voice,
    set_custom_profile,
    get_available_voices,
    get_hf_direct_ws_url,
    parse_hf_realtime_url,
    get_hf_connection_selection,
)
from reachy_mini_conversation_app.prompts import (
    get_session_voice,
    get_session_language,
    get_session_instructions,
    get_session_greeting_prompt,
)
from reachy_mini_conversation_app.streaming import AdditionalOutputs, audio_to_int16
from reachy_mini_conversation_app.audio.local_vad import SileroVAD
from reachy_mini_conversation_app.tools.core_tools import (
    ToolSpec,
    ToolDependencies,
    get_tool_specs,
)
from reachy_mini_conversation_app.document_retrieval import validate_document_result
from reachy_mini_conversation_app.conversation_handler import VADStatus, ConversationHandler
from reachy_mini_conversation_app.tools.background_tool_manager import (
    ToolCallRoutine,
    ToolNotification,
    BackgroundToolManager,
)


if TYPE_CHECKING:
    from openai.resources.realtime.realtime import AsyncRealtimeConnection


logger = logging.getLogger(__name__)

_RESPONSE_DONE_TIMEOUT: Final[float] = 30.0
_RESPONSE_REJECTION_RETRY_DELAY: Final[float] = 0.5
# A microphone frame that cannot be sent for this long means a dead link.
AUDIO_SEND_TIMEOUT_S: Final[float] = 5.0
SETUP_TIMEOUT_S: Final[float] = 15.0
CLOSE_TIMEOUT_S: Final[float] = 5.0
# Server-measured stage timings the speech-to-speech backend attaches to response.done.
_TURN_LATENCY_METADATA_KEY: Final[str] = "speech_to_speech.turn_latency"


class InputTranscriptChunksByItem(BaseModel):
    """Current item_id and its accumulated deltas. Only one item at a time."""

    item_id: str | None = None
    deltas: list[str] = Field(default_factory=list)


def to_realtime_tools_config(tool_specs: list[ToolSpec]) -> RealtimeToolsConfigParam:
    """Convert app tool specs to the OpenAI-compatible realtime session shape."""
    realtime_tools: RealtimeToolsConfigParam = []
    for spec in tool_specs:
        realtime_tools.append(
            RealtimeFunctionToolParam(
                type="function",
                name=spec["name"],
                description=spec["description"],
                parameters=spec["parameters"],
            )
        )
    return realtime_tools


class HFNativeRateAudioPCM(TypedDict):
    """Hugging Face extension for native-rate PCM audio."""

    type: Literal["audio/pcm"]
    rate: None


def _native_rate_audio_pcm() -> HFNativeRateAudioPCM:
    """Return the Hugging Face native-rate PCM config."""
    return {"type": "audio/pcm", "rate": None}


def _abort_realtime_connection(connection: Any) -> None:
    """Drop the realtime websocket's socket at once.

    A graceful close() would queue behind the stuck write. The session loop then
    sees the connection closed and takes its usual reconnect path.
    """
    try:
        # The OpenAI SDK keeps the websockets connection private.
        connection._connection.transport.abort()
    except Exception as e:
        logger.warning("Could not abort the realtime connection: %s", e)


def _parse_turn_latency(metadata: dict[str, str] | None) -> dict[str, int | str | None] | None:
    """Convert response.done turn-latency metadata to ms; None when absent or malformed."""
    raw = (metadata or {}).get(_TURN_LATENCY_METADATA_KEY)
    if raw is None:
        return None
    try:
        turn_latency = json.loads(raw)
    except (TypeError, ValueError) as e:
        logger.warning("Ignoring malformed turn latency metadata: %s", e)
        return None
    if not isinstance(turn_latency, dict):
        return None
    latency: dict[str, int | str | None] = {}
    for stage in ("vad_decision", "stt", "llm", "tts_ttfa", "e2e", "hold"):
        seconds = turn_latency.get(f"{stage}_s")
        if isinstance(seconds, (int, float)) and math.isfinite(seconds):
            latency[f"{stage}_ms"] = round(seconds * 1000)
        else:
            latency[f"{stage}_ms"] = None
    for status_field in ("smart_status", "status"):
        value = turn_latency.get(status_field)
        latency[status_field] = value if isinstance(value, str) else None
    return latency


def _build_openai_compatible_client_from_realtime_url(
    realtime_url: str,
    bearer_token: str | None,
) -> tuple[AsyncOpenAI, dict[str, str]]:
    """Build an OpenAI-compatible realtime client from a direct websocket/base URL."""
    parsed = parse_hf_realtime_url(realtime_url)
    client = AsyncOpenAI(
        api_key=bearer_token or "DUMMY",
        base_url=parsed.base_url,
        websocket_base_url=parsed.websocket_base_url,
    )
    return client, parsed.connect_query


@dataclass
class ToolInvocation:
    """Track one tool action across reconnects without repeating its effects."""

    tool_name: str
    status: Literal["received", "running", "completed", "cancelled", "uncertain"] = "received"
    result: dict[str, object] | None = None
    generation: int = 0
    response_epoch: int = 0
    uncertainty_reported: bool = False
    answer_retired: bool = False
    timeout_notice_sent: bool = False
    legacy_notice_sent: bool = False


class DocumentOutput(AdditionalOutputs):
    """Keep queued document text bound to its original conversation turn."""

    def __init__(self, invocation: ToolInvocation, text: str) -> None:
        """Attach ownership without exposing it in the displayed message."""
        super().__init__({"role": "assistant", "content": text})
        self.invocation = invocation


class DocumentResponse(dict[str, object]):
    """Keep a queued HF follow-up bound to the document turn that requested it."""

    def __init__(self, invocation: ToolInvocation) -> None:
        """Use normal response defaults while retaining local ownership metadata."""
        super().__init__(response={})
        self.invocation = invocation


@dataclass
class RealtimeSessionState:
    """Keep logical conversation state independently of replaceable sockets."""

    provider: str = "huggingface"
    revision: str = ""
    logical_session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    generation: int = 0
    response_epoch: int = 0
    resumption_handle: str | None = field(default=None, repr=False)
    resumable: bool = False
    context_state: Literal["new", "resumed", "unavailable"] = "new"
    invocations: dict[str, ToolInvocation] = field(default_factory=dict)

    def mark_uncertain_actions(self) -> bool:
        """Mark unfinished effects and return whether they need an uncertainty notice."""
        notification_needed = False
        for invocation in self.invocations.values():
            if invocation.tool_name == "search_document":
                invocation.answer_retired = True
                invocation.status = "cancelled"
                continue
            if invocation.status in ("received", "running", "uncertain"):
                invocation.status = "uncertain"
                if not invocation.uncertainty_reported:
                    invocation.uncertainty_reported = True
                    notification_needed = True
        return notification_needed

    def begin_connection(self) -> int:
        """Invalidate previous connection ownership while retaining logical context."""
        for invocation in self.invocations.values():
            if invocation.tool_name == "search_document":
                invocation.answer_retired = True
                invocation.status = "cancelled"
        self.generation += 1
        return self.generation

    def fresh(self, provider: str, revision: str) -> None:
        """Retire context and tool IDs without reusing connection generations."""
        self.generation += 1
        self.provider = provider
        self.response_epoch += 1
        self.revision = revision
        self.logical_session_id = uuid.uuid4().hex
        self.resumption_handle = None
        self.resumable = False
        self.context_state = "new"
        self.invocations.clear()


class RealtimeConversationHandler(ConversationHandler):
    """Share app playback, VAD and tool lifecycle across realtime providers."""

    session_state: RealtimeSessionState

    def __init__(self, deps: ToolDependencies, session_state: RealtimeSessionState | None = None) -> None:
        """Initialize shared state without connecting to a provider."""
        super().__init__()
        self.deps = deps
        self.session_state = session_state or RealtimeSessionState()
        self.playback_epoch = self.session_state.response_epoch
        self._generation = self.session_state.generation
        self._closed = False
        self.output_queue: asyncio.Queue[Tuple[int, NDArray[np.int16]] | AdditionalOutputs] = asyncio.Queue()
        self.tool_manager = BackgroundToolManager()
        self._local_vad: SileroVAD | None = None
        self._local_speech = False
        self._server_speech = False
        self._movement_listening = False
        self._local_audio_at: float | None = None
        self._last_vad_report_at = 0.0
        self._last_vad_flags: tuple[bool | float, ...] | None = None
        self._local_speech_timeout: asyncio.TimerHandle | None = None
        self._audio_response_id: str | None = None
        self._playback_interrupted = False
        self.paced_playback = config.LOCAL_VAD_ENABLED and config.LOCAL_BARGE_IN_ENABLED

    def _owns_connection(self) -> bool:
        return not self._closed and self._generation == self.session_state.generation

    def _document_current(self, invocation: ToolInvocation) -> bool:
        return (
            self._owns_connection()
            and invocation.generation == self._generation
            and invocation.response_epoch == self.playback_epoch
            and invocation.status != "cancelled"
            and "search_document" in core_tools.get_tools()
        )

    def _retire_document_calls(self) -> None:
        for invocation in self.session_state.invocations.values():
            if invocation.tool_name == "search_document":
                invocation.answer_retired = True
                invocation.status = "cancelled"

    def _document_result(self, notification: ToolNotification) -> dict[str, object] | None:
        invocation = self.session_state.invocations.get(notification.id)
        if invocation is None or invocation.status != "running" or not self._document_current(invocation):
            if invocation is not None:
                invocation.answer_retired = True
            return None
        if notification.error == "Tool cancelled":
            invocation.status = "cancelled"
            invocation.answer_retired = True
            return None
        validated = True
        try:
            result = validate_document_result(
                {"error": notification.error} if notification.error is not None else notification.result
            )
        except ValueError:
            logger.warning("Document tool result rejected: document_unavailable")
            validated = False
            result = {"error": "document_unavailable"}
        invocation.result = result
        invocation.status = "completed"
        if result.get("error") == "document_timeout":
            invocation.answer_retired = True
            if not invocation.timeout_notice_sent:
                invocation.timeout_notice_sent = True
                self.output_queue.put_nowait(DocumentOutput(invocation, "文件查詢已逾時，請稍後再試。"))
        runtime = self.deps.document_retrieval
        if (
            validated
            and result.get("error") == "document_unavailable"
            and runtime is not None
            and runtime.unavailable_reason == "legacy_package"
            and not invocation.legacy_notice_sent
        ):
            invocation.legacy_notice_sent = True
            self.output_queue.put_nowait(
                DocumentOutput(
                    invocation,
                    "此文件索引為舊版，請停止 App，使用離線產包腳本重新產生新版索引包。",
                )
            )
        return result

    async def emit(self) -> tuple[int, NDArray[np.int16]] | AdditionalOutputs | None:
        """Drop document text whose original turn retired before queue consumption."""
        output = await super().emit()
        if isinstance(output, DocumentOutput) and not self._document_current(output.invocation):
            return None
        return output

    @abstractmethod
    def _abort_connection(self) -> None:
        """Drop the failed provider transport after relinquishing media ownership."""
        ...

    async def _bounded_send(self, operation: Awaitable[None]) -> None:
        pending_send = asyncio.ensure_future(operation)
        try:
            if not self._owns_connection():
                raise ConnectionError("Retired conversation")
            completed, _pending = await asyncio.wait({pending_send}, timeout=AUDIO_SEND_TIMEOUT_S)
            if not completed:
                self.connection_error_reason = "send_timeout"
                if self._owns_connection():
                    self.session_state.begin_connection()
                self._closed = True
                self._abort_connection()
                raise TimeoutError("send_timeout")
            await pending_send
        finally:
            if not pending_send.done():
                pending_send.cancel()
                pending_send.add_done_callback(self._consume_send)

    @staticmethod
    def _consume_send(pending_send: asyncio.Future[None]) -> None:
        if not pending_send.cancelled() and pending_send.exception() is not None:
            logger.warning("Retired realtime send ended with an error")

    async def _flush_playback(self) -> None:
        if not self._owns_connection():
            return
        self._retire_document_calls()
        self.deps.movement_manager.set_speaking(False)
        if self._clear_queue is not None:
            await self._clear_queue()
        else:
            self.playback_epoch += 1
            self.session_state.response_epoch = self.playback_epoch
            while not self.output_queue.empty():
                self.output_queue.get_nowait()
        self.playback_gain = 1.0

    def _set_listening(self, *, local: bool | None = None, server: bool | None = None) -> None:
        if local is not None:
            self._local_speech = local
            if not local:
                self.playback_gain = 1.0
        if server is not None:
            self._server_speech = server
        listening = self._local_speech or self._server_speech
        if listening != self._movement_listening:
            self._movement_listening = listening
            self.deps.movement_manager.set_listening(listening)

        self._report_vad()

    def _report_vad(self) -> None:
        observer = self._vad_observer
        if observer is None or not logger.isEnabledFor(logging.DEBUG):
            return
        detector = self._local_vad
        candidate = detector is not None and detector.barge_in_candidate
        flags = (
            detector is not None,
            self._local_speech,
            self._server_speech,
            self._movement_listening,
            candidate,
            self.playback_gain,
        )
        now = time.monotonic()
        if flags == self._last_vad_flags and now - self._last_vad_report_at < 0.1:
            return
        self._last_vad_flags = flags
        self._last_vad_report_at = now
        status: VADStatus = {
            "timestamp": time.time(),
            "available": detector is not None,
            "probability": detector.speech_probability if detector is not None else None,
            "local_speech": self._local_speech,
            "server_speech": self._server_speech,
            "listening": self._movement_listening,
            "barge_in_candidate": candidate,
            "playback_gain": self.playback_gain,
        }
        try:
            observer(status)
        except Exception as exc:
            logger.warning("VAD observer failed: %s", exc)

    def _reset_listening(self) -> None:
        if self._local_speech_timeout is not None:
            self._local_speech_timeout.cancel()
            self._local_speech_timeout = None
        if self._local_vad is not None:
            self._local_vad.reset()
        self._local_audio_at = None
        self._set_listening(local=False, server=False)

    def _process_local_audio(self, sample_rate: int, audio_frame: NDArray[np.int16]) -> None:
        if self._local_vad is not None:
            if self._local_speech_timeout is not None:
                self._local_speech_timeout.cancel()
                self._local_speech_timeout = None
            received_at = time.monotonic()
            if self._local_audio_at is not None and received_at - self._local_audio_at > 0.5:
                self._local_vad.reset()
            self._local_audio_at = received_at
            detect_barge_in = (
                self.paced_playback
                and not self._playback_interrupted
                and self._audio_response_id is not None
                and (self.playback_until > received_at or self.playback_pending_frames > 0)
            )
            try:
                # Inline: ~2 ms per 32 ms chunk, cheaper than a thread hop on every frame.
                local_speech = self._local_vad.process(audio_frame, sample_rate, detect_barge_in=detect_barge_in)
            except Exception as exc:
                logger.warning("Local VAD failed; using server VAD for movement: %s", exc)
                self._local_vad = None
                self.paced_playback = False
                local_speech = False
            self._set_listening(local=local_speech)
            if self.paced_playback and self._local_vad is not None and not self._playback_interrupted:
                # Only duck: stopping waits for server VAD, so loud background speech cannot drop the turn.
                self.playback_gain = 0.25 if detect_barge_in and self._local_vad.barge_in_candidate else 1.0
            self._report_vad()
            if local_speech:
                # Muting or losing the microphone must not leave a stale local vote.
                self._local_speech_timeout = asyncio.get_running_loop().call_later(
                    0.5, lambda: self._set_listening(local=False)
                )


class HuggingFaceRealtimeHandler(RealtimeConversationHandler):
    """Realtime stream handler for the Hugging Face OpenAI-compatible endpoint."""

    SAMPLE_RATE = 16000

    def __init__(
        self,
        deps: ToolDependencies,
        instance_path: Optional[str] = None,
        startup_voice: Optional[str] = None,
        session_state: RealtimeSessionState | None = None,
    ) -> None:
        """Initialize the handler."""
        super().__init__(deps, session_state)

        self.client: AsyncOpenAI
        self.connection: "AsyncRealtimeConnection | None" = None

        self.instance_path = instance_path
        self._voice_override: str | None = self._normalize_startup_voice(startup_voice)
        self._realtime_connect_query: dict[str, str] = {}

        # Debouncing for partial transcripts
        self.partial_transcript_task: asyncio.Task[None] | None = None
        self.partial_debounce_delay = 0.5  # seconds
        self.input_transcript_chunks_by_item = InputTranscriptChunksByItem()

        # Internal lifecycle flags
        self._connected_event: asyncio.Event = asyncio.Event()

        # Response-in-progress guard: the Realtime API only allows one active
        # response per conversation at a time.  A dedicated worker task
        # (_response_sender_loop) dequeues and sends one request at a time
        self._pending_responses: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._response_done_event: asyncio.Event = asyncio.Event()
        self._response_done_event.set()
        self._response_started_or_rejected_event: asyncio.Event = asyncio.Event()
        self._last_response_rejected: bool = False
        self._turn_user_done_at: float | None = None
        self._turn_response_created_at: float | None = None
        self._turn_first_audio_at: float | None = None
        self._startup_greeting_sent = False
        self._in_flight_tool_calls: set[str] = set()
        self._tool_batch_needs_response = False
        self._active_response_id: str | None = None
        self._audio_response_id: str | None = None
        self._discarded_response_ids: deque[str] = deque(maxlen=32)
        self._playback_interrupted = False

    async def _interrupt_playback(
        self, *, audio_response_id: str | None = None, cancel_response_id: str | None = None
    ) -> None:
        if audio_response_id is not None and audio_response_id != self._audio_response_id:
            return
        self._retire_document_calls()
        if self._playback_interrupted:
            return
        self._playback_interrupted = True
        self.playback_gain = 0.0
        self._report_vad()
        self.deps.movement_manager.set_speaking(False)
        response_ids = (
            (audio_response_id, cancel_response_id)
            if audio_response_id is not None
            else (self._audio_response_id, self._active_response_id)
        )
        for response_id in response_ids:
            if response_id is not None and response_id not in self._discarded_response_ids:
                self._discarded_response_ids.append(response_id)
        try:
            if (
                cancel_response_id is not None
                and cancel_response_id == self._active_response_id
                and self.connection is not None
            ):
                await self._bounded_send(self.connection.response.cancel(response_id=cancel_response_id))
        except (ConnectionClosed, httpx.HTTPError, OSError) as exc:
            logger.warning("Failed to cancel locally interrupted response: %s", exc)
        finally:
            await self._flush_playback()

    @staticmethod
    def _sanitize_tool_result_for_model(tool_name: str, tool_result: dict[str, Any]) -> dict[str, Any]:
        """Remove bulky transport-only fields before echoing tool output back to the model."""
        if tool_name == "camera" and "b64_im" in tool_result:
            sanitized = dict(tool_result)
            sanitized.pop("b64_im", None)
            sanitized["image_attached"] = True
            return sanitized
        return tool_result

    def _normalize_startup_voice(self, voice: str | None) -> str | None:
        """Return a valid persisted startup voice, or None."""
        return self._resolve_backend_voice(voice, source="persisted startup voice")

    async def _wait_for_response_done_before_tool_result(self) -> bool:
        """Return whether the function-call response finished before sending tool output."""
        if self._response_done_event.is_set():
            return True

        try:
            await asyncio.wait_for(
                self._response_done_event.wait(),
                timeout=_RESPONSE_DONE_TIMEOUT,
            )
            return True
        except asyncio.TimeoutError:
            return False

    def _resolve_backend_voice(
        self,
        voice: str | None,
        *,
        source: str,
        fallback: str | None = None,
    ) -> str | None:
        """Return a backend-supported voice, optionally falling back when unsupported."""
        available_voices = get_available_voices()
        voice_value = (voice or "").strip()
        if not voice_value:
            return fallback

        voice_by_lowercase = {candidate.lower(): candidate for candidate in available_voices}
        normalized_voice = voice_by_lowercase.get(voice_value.lower())
        if normalized_voice is not None:
            return normalized_voice

        if voice:
            logger.warning(
                "Ignoring unsupported %s %r; expected one of %s",
                source,
                voice,
                available_voices,
            )
        return fallback

    def _get_session_config(self, tool_specs: list[ToolSpec]) -> RealtimeSessionCreateRequestParam:
        """Return the Hugging Face OpenAI-compatible session config."""
        return RealtimeSessionCreateRequestParam(
            type="realtime",
            instructions=get_session_instructions(self.instance_path),
            audio=RealtimeAudioConfigParam(
                input=RealtimeAudioConfigInputParam(
                    # The OpenAI SDK type only includes 24 kHz PCM, but the HF
                    # compatible server uses rate=None for native 16 kHz mode.
                    format=_native_rate_audio_pcm(),  # type: ignore[typeddict-item]
                    transcription=AudioTranscriptionParam(
                        model="gpt-4o-transcribe",
                        language=get_session_language(),
                    ),
                    turn_detection=ServerVad(type="server_vad", interrupt_response=True),
                ),
                output=RealtimeAudioConfigOutputParam(
                    format=_native_rate_audio_pcm(),  # type: ignore[typeddict-item]
                    voice=self.get_current_voice(),
                ),
            ),
            tools=to_realtime_tools_config(tool_specs),
            tool_choice="auto",
        )

    def _is_connected(self) -> bool:
        """Return whether the realtime connection is open."""
        return self.connection is not None and self._owns_connection()

    def _abort_connection(self) -> None:
        if self.connection is not None:
            _abort_realtime_connection(self.connection)

    def _idle_behavior_ready(self) -> bool:
        """Hold idle behavior while a model response is still active."""
        return self._response_done_event.is_set()

    async def _cancel_partial_transcript_task(self) -> None:
        if self.partial_transcript_task and not self.partial_transcript_task.done():
            self.partial_transcript_task.cancel()
            try:
                await self.partial_transcript_task
            except asyncio.CancelledError:
                pass

    async def change_voice(self, voice: str) -> str:
        """Change only the voice, updating the active session when possible."""
        default_voice = get_default_voice()
        resolved_voice = (
            self._resolve_backend_voice(voice, source="requested voice", fallback=default_voice) or default_voice
        )
        self._voice_override = resolved_voice
        if self.connection is not None:
            try:
                await self._bounded_send(
                    self.connection.session.update(
                        session=RealtimeSessionCreateRequestParam(
                            type="realtime",
                            audio=RealtimeAudioConfigParam(
                                output=RealtimeAudioConfigOutputParam(
                                    voice=resolved_voice,
                                ),
                            ),
                        ),
                    )
                )
                return f"聲音已變更為 {resolved_voice}。"
            except Exception as e:
                logger.warning("Failed to update live session for voice change: %s", e)
                return "聲音變更失敗，將於下次連線生效。"
        return "聲音已變更，將於下次連線生效。"

    def get_current_voice(self) -> str:
        """Return the voice currently selected for this handler."""
        default_voice = get_default_voice()
        voice = self._voice_override or get_session_voice(default=default_voice)
        return self._resolve_backend_voice(voice, source="session voice", fallback=default_voice) or default_voice

    async def refresh_instructions(self) -> bool:
        """Push freshly built instructions to the live session, if there is one."""
        if self.connection is None:
            return False
        await self._bounded_send(
            self.connection.session.update(
                session=RealtimeSessionCreateRequestParam(
                    type="realtime",
                    instructions=get_session_instructions(self.instance_path),
                ),
            )
        )
        logger.info("Refreshed session instructions")
        return True

    async def apply_personality(self, profile: str | None) -> str:
        """Apply a personality to the active or next realtime connection."""
        previous_profile = config.REACHY_MINI_CUSTOM_PROFILE
        set_custom_profile(profile)
        try:
            instructions = get_session_instructions(self.instance_path)
            voice = self.get_current_voice()
            core_tools.initialize_tools(force=True)
        except Exception as exc:
            set_custom_profile(previous_profile)
            logger.error("Failed to resolve personality %r: %s", profile, exc)
            return f"套用人格失敗：{exc}"

        if self.connection is not None:
            try:
                await self._bounded_send(
                    self.connection.session.update(
                        session=RealtimeSessionCreateRequestParam(
                            type="realtime",
                            instructions=instructions,
                            audio=RealtimeAudioConfigParam(
                                output=RealtimeAudioConfigOutputParam(
                                    voice=voice,
                                ),
                            ),
                        ),
                    )
                )
                logger.info("Applied personality via live update: %s", profile or "default")
            except Exception as exc:
                logger.warning("Live update failed; will restart session: %s", exc)

            try:
                await self._restart_session()
                return "人格已套用，並已重新啟動即時對話。"
            except Exception as exc:
                logger.warning("Failed to restart session after apply: %s", exc)
                return "人格已套用，將於下次連線生效。"

        logger.info(
            "Applied personality recorded: %s (no live connection; will apply on next session)",
            profile or "default",
        )
        return "人格已套用，將於下次連線生效。"

    async def _emit_debounced_partial(self, transcript: str, item_id: str, sequence_counter: int) -> None:
        """Emit partial transcript after debounce delay."""
        try:
            await asyncio.sleep(self.partial_debounce_delay)

            input_transcript = self.input_transcript_chunks_by_item
            if input_transcript.item_id == item_id and len(input_transcript.deltas) - 1 == sequence_counter:
                await self.output_queue.put(AdditionalOutputs({"role": "user_partial", "content": transcript}))
                self._emit_transcript("user", transcript, False)
                logger.debug(f"Debounced partial emitted: {transcript}")
        except asyncio.CancelledError:
            logger.debug("Debounced partial cancelled")
            raise

    def _record_partial_transcript_delta(
        self,
        input_transcript: InputTranscriptChunksByItem,
        item_id: str,
        delta: str,
    ) -> None:
        """Append an incremental partial transcript fragment for one item."""
        if input_transcript.item_id != item_id:
            input_transcript.item_id = item_id
            input_transcript.deltas = [delta]
            return
        input_transcript.deltas.append(delta)

    async def start_up(self) -> None:
        """Run one connection attempt; LocalStream owns recovery."""
        if config.LOCAL_VAD_ENABLED:
            try:
                self._local_vad = await asyncio.to_thread(SileroVAD)
            except Exception as exc:
                logger.warning("Local VAD unavailable; using server VAD for movement: %s", exc)
                self.paced_playback = False
        self.client = await self._build_realtime_client()

        self._closed = False
        try:
            await self._run_realtime_session()
        finally:
            self.connection = None
            self._connected_event.clear()

    async def _restart_session(self) -> None:
        """Force-close the current session and start a fresh one in background.

        Does not block the caller while the new session is establishing.
        """
        try:
            if self.connection is not None:
                try:
                    await self.connection.close()
                except Exception:
                    pass
                finally:
                    self.connection = None

            # Ensure we have a client (start_up must have run once)
            if getattr(self, "client", None) is None:
                logger.warning("Cannot restart: realtime client not initialized yet.")
                return

            # Fire-and-forget new session and wait briefly for connection
            try:
                self._connected_event.clear()
            except Exception:
                pass
            self.client = await self._build_realtime_client()
            asyncio.create_task(self._run_realtime_session(), name="realtime-session-restart")
            try:
                await asyncio.wait_for(self._connected_event.wait(), timeout=5.0)
                logger.info("Realtime session restarted and connected.")
            except asyncio.TimeoutError:
                logger.warning("Realtime session restart timed out; continuing in background.")
        except Exception as e:
            logger.warning("_restart_session failed: %s", e)

    async def _safe_response_create(self, **kwargs: Any) -> None:
        """Enqueue a response.create() kwargs for the sender worker _response_sender_loop().

        This method never blocks the caller.
        """
        await self._pending_responses.put(kwargs)

    async def interrupt(self) -> None:
        """Stop playback and cancel the response still being generated."""
        if not self._owns_connection():
            return
        await self._interrupt_playback(cancel_response_id=self._active_response_id)

    async def say(self, text: str) -> None:
        """Inject ``text`` as a turn and have the model voice it now.

        Mirrors the startup-greeting path: create a user message item, then
        queue a ``response.create`` through the serial sender. Not verbatim TTS
        (speech-to-speech may rephrase). Raises if the session is closed.
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("say: empty text")
        if not self.connection:
            raise RuntimeError("say: no active session")
        self._retire_document_calls()
        await self._bounded_send(
            self.connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            )
        )
        self._mark_activity("say")
        await self._safe_response_create()

    async def _send_startup_greeting_prompt(self) -> None:
        """Prompt the model to open the conversation once the session is ready."""
        if self._startup_greeting_sent or not self.connection:
            return

        greeting_prompt = get_session_greeting_prompt().strip()
        if not greeting_prompt:
            self._startup_greeting_sent = True
            return

        try:
            await self._bounded_send(
                self.connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": greeting_prompt,
                            },
                        ],
                    },
                )
            )
            self._startup_greeting_sent = True
            self._mark_activity("startup_greeting_prompt")
            await self._safe_response_create()
            logger.info("Queued startup greeting prompt")
        except Exception as e:
            logger.warning("Failed to queue startup greeting prompt: %s", e)

    async def _response_sender_loop(self) -> None:
        """Dedicated worker that sends ``response.create()`` calls serially.

        This logic was designed to comply with the response.create() docstring specification for event ordering:
        https://github.com/openai/openai-python/blob/3e0c05b84a2056870abf3bd6a5e7849020209cc3/src/openai/resources/realtime/realtime.py#L649C1-L651C30

        For each queued request the worker:
        1. Waits until no response is active (_response_done_event).
        2. Sends response.create().
        3. Waits until the receiver observes response.created or a rejection.
        4. Waits for the response cycle to complete (response.done).
        5. If the server rejected with active_response, retries from step 1.
        """
        while self.connection:
            try:
                kwargs = await self._pending_responses.get()
            except asyncio.CancelledError:
                return

            # Parallel tool calls enqueue duplicate empty requests; coalesce to one.
            while not kwargs and not self._pending_responses.empty():
                try:
                    queued_response = self._pending_responses.get_nowait()
                    if queued_response:
                        self._pending_responses.put_nowait(queued_response)
                        break
                except asyncio.QueueEmpty:
                    break

            sent = False
            max_retries = 5
            attempts = 0
            while not sent and self.connection and attempts < max_retries:
                try:
                    await asyncio.wait_for(
                        self._response_done_event.wait(),
                        timeout=_RESPONSE_DONE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.debug("Timed out waiting for previous response to finish; forcing ahead")
                    self._response_done_event.set()

                if not self.connection:
                    break

                if isinstance(kwargs, DocumentResponse) and not self._document_current(kwargs.invocation):
                    break

                self._last_response_rejected = False
                self._response_started_or_rejected_event.clear()
                try:
                    await self._bounded_send(self.connection.response.create(**kwargs))
                except Exception as e:
                    logger.debug("_response_sender_loop: send failed: %s", e)
                    self._response_done_event.set()
                    break

                try:
                    await asyncio.wait_for(
                        self._response_started_or_rejected_event.wait(),
                        timeout=_RESPONSE_DONE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.debug("Timed out waiting for response.created or response rejection")

                # Check if the receiver loop observed an asynchronous rejection.
                if self._last_response_rejected:
                    attempts += 1
                    if attempts >= max_retries:
                        logger.debug("response.create rejected %d times; giving up", attempts)
                        break
                    logger.debug("response.create was rejected; retrying (%d/%d)", attempts, max_retries)
                    await asyncio.sleep(_RESPONSE_REJECTION_RETRY_DELAY)
                    continue

                try:
                    await asyncio.wait_for(
                        self._response_done_event.wait(),
                        timeout=_RESPONSE_DONE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.debug("Timed out waiting for response.done; assuming response completed")
                    self._response_done_event.set()
                    break

                sent = True

    async def _handle_document_result(self, notification: ToolNotification) -> None:
        result = self._document_result(notification)
        invocation = self.session_state.invocations.get(notification.id)
        try:
            if result is None or invocation is None or self.connection is None:
                return
            timeout = result.get("error") == "document_timeout"
            if not timeout:
                self.output_queue.put_nowait(DocumentOutput(invocation, json.dumps(result, ensure_ascii=False)))
            if not await self._wait_for_response_done_before_tool_result():
                return
            if not self._document_current(invocation) or self.connection is None:
                return
            await self._bounded_send(
                self.connection.conversation.item.create(
                    item={"type": "function_call_output", "call_id": notification.id, "output": json.dumps(result)}
                )
            )
            if not self._document_current(invocation):
                return
            self._in_flight_tool_calls.discard(notification.id)
            if not timeout:
                self._tool_batch_needs_response = True
            if self._tool_batch_needs_response and not self._in_flight_tool_calls:
                self._tool_batch_needs_response = False
                if timeout:
                    await self._safe_response_create()
                else:
                    self._pending_responses.put_nowait(DocumentResponse(invocation))
        except (OSError, httpx.HTTPError, ConnectionClosed):
            logger.warning("Document result transport unavailable")
        finally:
            self._in_flight_tool_calls.discard(notification.id)

    async def _handle_tool_result(self, completed_tool: ToolNotification) -> None:
        """Process the result of a tool call."""
        if completed_tool.tool_name == "search_document":
            await self._handle_document_result(completed_tool)
            return
        if not self._owns_connection():
            return
        if completed_tool.error is not None:
            logger.error(
                "Tool '%s' (id=%s) failed with error: %s",
                completed_tool.tool_name,
                completed_tool.id,
                completed_tool.error,
            )
            tool_result = {"error": completed_tool.error}
            tool_result_for_model = tool_result
        elif completed_tool.result is not None:
            tool_result = completed_tool.result
            tool_result_for_model = (
                self._sanitize_tool_result_for_model(completed_tool.tool_name, tool_result)
                if isinstance(tool_result, dict)
                else tool_result
            )
            logger.info(
                "Tool '%s' (id=%s) executed successfully.",
                completed_tool.tool_name,
                completed_tool.id,
            )
            logger.debug("Tool '%s' model-visible result: %s", completed_tool.tool_name, tool_result_for_model)
        else:
            logger.warning(
                "Tool '%s' (id=%s) returned no result and no error", completed_tool.tool_name, completed_tool.id
            )
            tool_result = {"error": "No result returned from tool execution"}
            tool_result_for_model = tool_result

        # Connection may have closed while tool was running
        if not self.connection:
            logger.warning(
                "Connection closed during tool '%s' (id=%s) execution; cannot send result back",
                completed_tool.tool_name,
                completed_tool.id,
            )
            return

        try:
            send_result_to_model = not completed_tool.is_idle_tool_call
            if send_result_to_model:
                self._mark_activity("tool_result_ready")
            model_result_submitted = False
            if send_result_to_model and isinstance(completed_tool.id, str):
                if not await self._wait_for_response_done_before_tool_result():
                    send_result_to_model = False
                if not send_result_to_model:
                    logger.warning(
                        "Dropping realtime model result for tool '%s' (id=%s) because response.done was not observed",
                        completed_tool.tool_name,
                        completed_tool.id,
                    )
                elif not self.connection:
                    logger.warning(
                        "Connection closed before sending tool '%s' (id=%s) result back",
                        completed_tool.tool_name,
                        completed_tool.id,
                    )
                    return
                else:
                    await self._bounded_send(
                        self.connection.conversation.item.create(
                            item={
                                "type": "function_call_output",
                                "call_id": completed_tool.id,
                                "output": json.dumps(tool_result_for_model),
                            },
                        )
                    )
                    model_result_submitted = True

            await self.output_queue.put(
                AdditionalOutputs(
                    {
                        "role": "assistant",
                        "content": json.dumps(tool_result_for_model),
                    },
                ),
            )

            if model_result_submitted and completed_tool.tool_name == "camera" and "b64_im" in tool_result:
                # use raw base64, don't json.dumps (which adds quotes)
                b64_im = tool_result["b64_im"]
                if not isinstance(b64_im, str):
                    logger.warning("Unexpected type for b64_im: %s", type(b64_im))
                    b64_im = str(b64_im)
                image_width = tool_result.get("image_width")
                image_height = tool_result.get("image_height")
                jpeg_bytes_value = tool_result.get("jpeg_bytes")
                jpeg_bytes = jpeg_bytes_value if isinstance(jpeg_bytes_value, int) else (len(b64_im) * 3) // 4
                await self._bounded_send(
                    self.connection.conversation.item.create(
                        item={
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_image",
                                    "image_url": f"data:image/jpeg;base64,{b64_im}",
                                },
                            ],
                        },
                    )
                )
                if isinstance(image_width, int) and isinstance(image_height, int):
                    logger.info(
                        "Added camera image to conversation frame=%sx%s jpeg_bytes=%s",
                        image_width,
                        image_height,
                        jpeg_bytes,
                    )
                else:
                    logger.info(
                        "Added camera image to conversation jpeg_bytes=%s",
                        jpeg_bytes,
                    )

            if isinstance(completed_tool.id, str):
                self._in_flight_tool_calls.discard(completed_tool.id)

            tool = core_tools.get_tools().get(completed_tool.tool_name)
            # Always surface errors, skip the spoken follow-up for tools that opt out.
            if model_result_submitted and (completed_tool.error is not None or tool is None or tool.needs_response):
                self._tool_batch_needs_response = True

            # Parallel tool calls in one turn: respond once every result is in, not per tool.
            if self._tool_batch_needs_response and not self._in_flight_tool_calls:
                self._tool_batch_needs_response = False
                await self._safe_response_create()

        except ConnectionClosedError:
            logger.warning("Connection closed while sending tool result")
            self.connection = None
            self._response_done_event.set()

    async def _run_realtime_session(self) -> None:
        """Establish and manage a single realtime session."""
        tool_specs = get_tool_specs()
        logger.info(
            "Tools to be used in conversation: %s",
            [tool["name"] for tool in tool_specs],
        )
        connect_kwargs: dict[str, Any] = {}
        if self._realtime_connect_query:
            connect_kwargs["extra_query"] = self._realtime_connect_query
        async with self.client.realtime.connect(**connect_kwargs) as conn:
            try:
                session_config = self._get_session_config(tool_specs)
                await self._bounded_send(conn.session.update(session=session_config))
                events = conn.__aiter__()
                async for setup_event in events:
                    if not self._owns_connection():
                        return
                    if setup_event.type == "error":
                        raise ValueError("Realtime session configuration rejected")
                    if setup_event.type == "session.updated":
                        break
                else:
                    raise ConnectionError("Realtime connection ended before setup acknowledgement")
                logger.info(
                    "Realtime session initialized with profile=%r voice=%r",
                    getattr(config, "REACHY_MINI_CUSTOM_PROFILE", None),
                    self.get_current_voice(),
                )
            except Exception as error:
                logger.warning("Realtime setup failed (%s)", type(error).__name__)
                raise

            logger.info("Realtime session updated successfully")

            # Reset the partial-transcript accumulator for each new session
            self.input_transcript_chunks_by_item = InputTranscriptChunksByItem()

            # Manage events received from the realtime server.
            self.connection = conn
            self._active_response_id = None
            self._audio_response_id = None
            self._discarded_response_ids.clear()
            self._playback_interrupted = False
            try:
                self._connected_event.set()
            except Exception:
                pass

            response_sender_task: asyncio.Task[None] | None = None
            try:
                # Start the background tool manager
                self.tool_manager.start_up(tool_callbacks=[self._handle_tool_result])

                # Start the response sender worker
                response_sender_task = asyncio.create_task(self._response_sender_loop(), name="response-sender")
                await self._send_startup_greeting_prompt()

                async for event in events:
                    if not self._owns_connection():
                        break
                    logger.debug("Realtime event: %s", event.type)
                    if event.type == "input_audio_buffer.speech_started":
                        self._mark_activity("user_speech_started")
                        self._turn_user_done_at = None
                        self._turn_response_created_at = None
                        self._turn_first_audio_at = None
                        await self._interrupt_playback()
                        self._set_listening(server=True)
                        logger.debug("User speech started")

                    if event.type == "input_audio_buffer.speech_stopped":
                        self._mark_activity("user_speech_stopped")
                        self._set_listening(server=False)
                        logger.debug("User speech stopped - server will auto-commit with VAD")

                    if event.type == "response.output_audio.done":
                        if event.response_id in self._discarded_response_ids:
                            continue
                        self.deps.movement_manager.set_speaking(False)
                        logger.debug("response completed")

                    if event.type == "response.output_text.delta":
                        logger.debug("response text delta")

                    if event.type == "response.output_text.done":
                        logger.debug("response text done: %s", event.text)

                    if event.type == "response.created":
                        self._active_response_id = event.response.id
                        self._playback_interrupted = False
                        self._mark_activity("response_created")
                        self.deps.movement_manager.set_speaking(True)
                        self._response_done_event.clear()
                        self._response_started_or_rejected_event.set()
                        if self._turn_user_done_at is not None and self._turn_response_created_at is None:
                            self._turn_response_created_at = time.perf_counter()
                            delta_ms = (self._turn_response_created_at - self._turn_user_done_at) * 1000
                            logger.info("Turn latency: response.created %.0f ms after user transcript", delta_ms)
                        logger.debug("Response created (active)")

                    if event.type == "response.done":
                        if self._active_response_id is not None and event.response.id != self._active_response_id:
                            continue
                        if event.response.status == "completed" and self._turn_first_audio_at is not None:
                            self.notify_exchange_completed()
                        if event.response.id == self._active_response_id:
                            self._active_response_id = None
                        # Doesn't mean the audio is done playing
                        # Resume tracking for responses that emit no audio (text-only / tool-only).
                        self.deps.movement_manager.set_speaking(False)
                        self._response_done_event.set()
                        self._response_started_or_rejected_event.set()
                        logger.debug("Response done")
                        latency = _parse_turn_latency(event.response.metadata)
                        if latency is not None:
                            self._emit_latency(latency)

                    if event.type == "conversation.item.input_audio_transcription.delta":
                        self._mark_activity("user_transcription_delta")
                        logger.debug(f"User partial transcript: {event.delta}")

                        item_id = event.item_id
                        delta = event.delta or ""

                        input_transcript = self.input_transcript_chunks_by_item
                        self._record_partial_transcript_delta(input_transcript, item_id, delta)

                        current_partial = "".join(input_transcript.deltas)
                        sequence_counter = len(input_transcript.deltas) - 1

                        await self._cancel_partial_transcript_task()

                        # Start new debounce timer with the last delta
                        self.partial_transcript_task = asyncio.create_task(
                            self._emit_debounced_partial(current_partial, item_id, sequence_counter)
                        )

                    # Handle completed transcription (user finished speaking)
                    if event.type == "conversation.item.input_audio_transcription.completed":
                        self._mark_activity("user_transcription_completed")
                        raw_transcript = event.transcript or ""
                        transcript = raw_transcript.strip()
                        logger.debug("User transcript: %s", raw_transcript)
                        self._set_listening(server=False)

                        await self._cancel_partial_transcript_task()

                        if not transcript:
                            logger.debug("Ignoring empty user transcript")
                            continue

                        self._turn_user_done_at = time.perf_counter()
                        self._turn_response_created_at = None
                        self._turn_first_audio_at = None
                        self._in_flight_tool_calls.clear()
                        self._tool_batch_needs_response = False

                        await self.output_queue.put(AdditionalOutputs({"role": "user", "content": transcript}))
                        self._emit_transcript("user", transcript, True)

                    # Handle assistant transcription
                    if event.type == "response.output_audio_transcript.done":
                        if event.response_id in self._discarded_response_ids:
                            continue
                        self._mark_activity("assistant_transcript_done")
                        logger.debug(f"Assistant transcript: {event.transcript}")
                        await self.output_queue.put(
                            AdditionalOutputs({"role": "assistant", "content": event.transcript})
                        )
                        self._emit_transcript("assistant", event.transcript or "", True)

                    # Handle audio delta
                    if event.type == "response.output_audio.delta":
                        if event.response_id in self._discarded_response_ids:
                            continue
                        self._audio_response_id = event.response_id
                        decoded_pcm_bytes = base64.b64decode(event.delta)
                        decoded_pcm = np.frombuffer(decoded_pcm_bytes, dtype=np.int16).reshape(1, -1)
                        self._mark_activity("assistant_audio_delta")
                        if self._turn_user_done_at is not None and self._turn_first_audio_at is None:
                            self._turn_first_audio_at = time.perf_counter()
                            delta_ms = (self._turn_first_audio_at - self._turn_user_done_at) * 1000
                            logger.info("Turn latency: first audio delta %.0f ms after user transcript", delta_ms)
                        self.playback_frame_epochs[id(decoded_pcm)] = self.playback_epoch
                        if self.paced_playback:
                            self.playback_pending_frames += 1
                        await self.output_queue.put(
                            (
                                self.SAMPLE_RATE,
                                decoded_pcm,
                            ),
                        )
                    # ---- tool-calling plumbing ----
                    if event.type == "response.function_call_arguments.done":
                        self._mark_activity("tool_call_received")
                        tool_name = getattr(event, "name", None)
                        args_json_str = getattr(event, "arguments", None)
                        call_id: str = str(getattr(event, "call_id", uuid.uuid4()))
                        logged_args = "[redacted]" if tool_name == "search_document" else args_json_str

                        logger.info(
                            "Tool call received — tool_name=%r, call_id=%s, args=%s",
                            tool_name,
                            call_id,
                            logged_args,
                        )

                        if not isinstance(tool_name, str) or not isinstance(args_json_str, str):
                            logger.error(
                                "Invalid tool call: tool_name=%s (type=%s), args=%s (type=%s), call_id=%s",
                                tool_name,
                                type(tool_name).__name__,
                                logged_args,
                                type(args_json_str).__name__,
                                call_id,
                            )
                            continue

                        if tool_name == "search_document":
                            if call_id in self.session_state.invocations:
                                continue
                            self.session_state.invocations[call_id] = ToolInvocation(
                                tool_name, "running", generation=self._generation, response_epoch=self.playback_epoch
                            )
                        self._in_flight_tool_calls.add(call_id)
                        background_tool = await self.tool_manager.start_tool(
                            call_id=call_id,
                            tool_call_routine=ToolCallRoutine(
                                tool_name=tool_name,
                                args_json_str=args_json_str,
                                deps=self.deps,
                            ),
                            is_idle_tool_call=False,
                        )

                        await self.output_queue.put(
                            AdditionalOutputs(
                                {
                                    "role": "assistant",
                                    "content": (
                                        "正在查詢指定文件。"
                                        if tool_name == "search_document"
                                        else f"🛠️ Used tool {tool_name} with args {args_json_str}. The tool is now running. Tool ID: {background_tool.tool_id}"
                                    ),
                                },
                            ),
                        )
                        logger.info(
                            "Started background tool: %s (id=%s, call_id=%s)",
                            tool_name,
                            background_tool.tool_id,
                            call_id,
                        )

                    # server error
                    if event.type == "error":
                        err = getattr(event, "error", None)
                        code = getattr(err, "code", "") or getattr(err, "type", "")

                        if code == "conversation_already_has_active_response":
                            # response.create was rejected.  The sender worker
                            # is waiting on _response_done_event; when the active
                            # response finishes it will wake up and see this flag.
                            self._last_response_rejected = True
                            self._response_started_or_rejected_event.set()
                            logger.debug("response.create rejected; worker will retry after active response finishes")
                        else:
                            self._response_started_or_rejected_event.set()
                            logger.error("Realtime service reported an error")

                        if code == "input_audio_buffer_commit_empty":
                            self._set_listening(server=False)

                        # Only show user-facing errors, not internal state errors.
                        if code not in (
                            "input_audio_buffer_commit_empty",
                            "conversation_already_has_active_response",
                        ):
                            await self.output_queue.put(
                                AdditionalOutputs(
                                    {
                                        "role": "assistant",
                                        "content": "[error] Realtime service error. Check configuration and retry.",
                                    }
                                )
                            )
            finally:
                self.connection = None
                self._reset_listening()
                self._active_response_id = None
                self._audio_response_id = None
                # Stop the response sender worker.
                if response_sender_task is not None:
                    response_sender_task.cancel()
                    try:
                        await response_sender_task
                    except asyncio.CancelledError:
                        pass

                # Stop background tool manager tasks (listener + cleanup) in all paths.
                await self.tool_manager.shutdown()

    # Microphone receive
    async def receive(self, frame: Tuple[int, NDArray[np.int16]]) -> None:
        """Receive audio frame from the microphone and send it to the realtime server.

        Handles both mono and stereo audio formats, converting to the expected
        mono format for the realtime API.

        Args:
            frame: A tuple containing (sample_rate, audio_data).

        """
        sample_rate, audio_frame = frame
        if audio_frame.size == 0:
            return

        # Reshape if needed
        if audio_frame.ndim == 2:
            # channels-last convention
            if audio_frame.shape[1] > audio_frame.shape[0]:
                audio_frame = audio_frame.T
            # Multiple channels -> Mono channel
            if audio_frame.shape[1] > 1:
                audio_frame = audio_frame[:, 0]

        # Cast if needed
        audio_frame = audio_to_int16(audio_frame)

        connection = self.connection
        if connection and self._owns_connection():
            # Send to the realtime input buffer (guard against races during reconnect).
            try:
                audio_message = base64.b64encode(audio_frame.tobytes()).decode("utf-8")
                await self._bounded_send(connection.input_audio_buffer.append(audio=audio_message))
            except TimeoutError:
                # On a dead link the socket buffer fills, and every send, the websocket
                # keepalive ping included, then waits for it to drain: without this the
                # drop only surfaces once TCP gives up.
                logger.warning("Realtime audio send stuck for %.0f s; dropping the connection", AUDIO_SEND_TIMEOUT_S)
            except Exception as e:
                logger.debug("Dropping audio frame: connection not ready (%s)", e)

        self._process_local_audio(sample_rate, audio_frame)

    async def shutdown(self) -> None:
        """Shutdown the handler."""
        self._closed = True
        self._reset_listening()
        self._local_vad = None
        # Unblock the response sender worker so it can exit
        self._response_done_event.set()

        # Stop background tool manager tasks (listener + cleanup)
        await self.tool_manager.shutdown()

        await self._cancel_partial_transcript_task()

        if self.connection:
            try:
                await self.connection.close()
            except ConnectionClosedError as e:
                logger.debug(f"Connection already closed during shutdown: {e}")
            except Exception as e:
                logger.debug(f"connection.close() ignored: {e}")
            finally:
                self.connection = None

        # Clear any remaining items in the output queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def get_available_voices(self) -> list[str]:
        """Return the available Hugging Face voices."""
        return get_available_voices()

    async def _build_realtime_client(self) -> AsyncOpenAI:
        """Build the Hugging Face OpenAI-compatible realtime client."""
        configured_bearer_token = (config.HF_TOKEN or "").strip()
        connection_selection = get_hf_connection_selection()
        direct_realtime_url = get_hf_direct_ws_url()
        if connection_selection.mode == HF_LOCAL_CONNECTION_MODE:
            if not direct_realtime_url:
                raise RuntimeError("HF_REALTIME_WS_URL must be set when HF_REALTIME_CONNECTION_MODE=local")
            client, connect_query = _build_openai_compatible_client_from_realtime_url(
                direct_realtime_url,
                configured_bearer_token,
            )
            self._realtime_connect_query = connect_query
            logger.info("Using direct Hugging Face realtime endpoint %s", direct_realtime_url)
            return client

        session_url = connection_selection.session_url
        if not session_url:
            raise RuntimeError("Built-in Hugging Face session proxy URL is unavailable")
        if direct_realtime_url:
            logger.info("HF_REALTIME_CONNECTION_MODE=deployed; ignoring HF_REALTIME_WS_URL.")

        bearer_token = configured_bearer_token or (get_token() or "").strip()
        allocator_headers = {"User-Agent": "reachy-mini-conversation-app"}
        if bearer_token:
            allocator_headers["X-Reachy-Mini-Authorization"] = f"Bearer {bearer_token}"
        allocator_payload: dict[str, str] = {}
        try:
            hardware_id = self.deps.reachy_mini.client.get_status(wait=False).hardware_id
        except (AssertionError, ConnectionError, TimeoutError) as e:
            logger.warning("Daemon status unavailable for realtime session allocation: %s", e)
        else:
            if hardware_id:
                allocator_payload["hardware_id"] = hardware_id

        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.post(session_url, headers=allocator_headers, json=allocator_payload)
            response.raise_for_status()
            payload = response.json()

        connect_url = payload.get("connect_url")
        if not isinstance(connect_url, str) or not connect_url:
            raise RuntimeError(f"Session allocator response did not contain a valid connect_url: {payload!r}")

        parsed_connect_url = parse_hf_realtime_url(connect_url)
        if not parsed_connect_url.has_realtime_path:
            raise ValueError(f"Expected realtime connect URL ending with /realtime, got: {connect_url}")

        logger.info("Allocated realtime session %s", payload.get("session_id") or "<unknown>")
        client, connect_query = _build_openai_compatible_client_from_realtime_url(
            connect_url,
            bearer_token,
        )
        self._realtime_connect_query = connect_query
        return client
