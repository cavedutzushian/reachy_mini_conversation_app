import re
import json
import time
import base64
import asyncio
import hashlib
import logging

import numpy as np
from jsonschema import SchemaError, Draft202012Validator
from websockets.exceptions import InvalidStatus, ConnectionClosed
from websockets.asyncio.client import ClientConnection, connect

from reachy_mini_conversation_app.config import GEMINI_AVAILABLE_VOICES, config, set_custom_profile
from reachy_mini_conversation_app.prompts import (
    get_session_voice,
    get_session_instructions,
    get_session_greeting_prompt,
)
from reachy_mini_conversation_app.streaming import AdditionalOutputs, audio_to_int16
from reachy_mini_conversation_app.audio.local_vad import SileroVAD
from reachy_mini_conversation_app.audio.resampling import AudioResampler
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies, get_tools, get_tool_specs
from reachy_mini_conversation_app.conversation_handler import AudioFrame
from reachy_mini_conversation_app.huggingface_realtime import (
    CLOSE_TIMEOUT_S,
    SETUP_TIMEOUT_S,
    ToolInvocation,
    RealtimeSessionState,
    RealtimeConversationHandler,
)
from reachy_mini_conversation_app.tools.volume_control import VOLUME_CHANGE_UNCERTAIN
from reachy_mini_conversation_app.tools.background_tool_manager import ToolCallRoutine, ToolNotification


logger = logging.getLogger(__name__)
transport_logger = logging.getLogger(__name__ + ".transport")
transport_logger.setLevel(logging.WARNING)
GEMINI_LIVE_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
TURN_BOUNDARY_TIMEOUT_S = 5.0


class GeminiConnectionError(ConnectionError):
    """Carry a safe recovery reason without retaining remote payloads."""

    def __init__(self, reason: str, *, recoverable: bool = True) -> None:
        """Initialize the connection state."""
        super().__init__(reason)
        self.reason = reason
        self.recoverable = recoverable


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return {}
    return {key: entry for key, entry in value.items() if isinstance(key, str)}


def _decode_message(message: str | bytes) -> dict[str, object]:
    parsed: object = json.loads(message)
    if not isinstance(parsed, dict):
        raise GeminiConnectionError("connection_lost")
    return _object(parsed)


class GeminiRealtimeHandler(RealtimeConversationHandler):
    """Translate Gemini Live messages into the application's shared conversation behavior."""

    def __init__(
        self,
        deps: ToolDependencies,
        instance_path: str | None = None,
        session_state: RealtimeSessionState | None = None,
        *,
        api_key: str | None = None,
    ) -> None:
        """Initialize the connection state."""
        super().__init__(deps, session_state or RealtimeSessionState(provider="gemini"))
        self.instance_path = instance_path
        self._api_key = api_key
        self.connection: ClientConnection | None = None
        self._ready = False
        self._send_lock = asyncio.Lock()
        self._draining = False
        self._barrier_deadline = 0.0
        self._assistant_text = ""
        self._input_text = ""
        self._aliases: dict[str, str] = {}
        self._validators: dict[str, Draft202012Validator] = {}
        self._silent_tools: set[str] = set()
        self._tool_ids: dict[str, str] = {}
        self._output_resampler: AudioResampler | None = None
        self._input_resampler: AudioResampler | None = None
        self._input_rate = 0
        self._output_rate = 24000
        self._logical_session_id = self.session_state.logical_session_id
        self._turn_active = False
        self._exchange_has_output = False

    def _is_connected(self) -> bool:
        return self._ready and self.connection is not None and self._owns_connection()

    def _idle_behavior_ready(self) -> bool:
        return not self._turn_active and self._is_connected()

    def _abort_connection(self) -> None:
        self._ready = False
        if self.connection is not None:
            self.connection.transport.abort()

    def get_current_voice(self) -> str:
        """Resolve the saved Gemini voice before the personality and environment defaults."""
        voice = config.GEMINI_VOICE_OVERRIDE or get_session_voice(default=config.GEMINI_VOICE or "Kore")
        if voice not in GEMINI_AVAILABLE_VOICES:
            raise ValueError("invalid_gemini_voice: select a compatible Gemini voice")
        return voice

    async def get_available_voices(self) -> list[str]:
        """Return the supported Gemini voice catalog."""
        return list(GEMINI_AVAILABLE_VOICES)

    def _declarations(self) -> list[dict[str, object]]:
        declarations: list[dict[str, object]] = []
        tools = get_tools()
        for spec in get_tool_specs():
            name = spec["name"]
            alias = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
            if alias != name or len(alias) > 128:
                alias = alias[:110] + "_" + hashlib.sha256(name.encode()).hexdigest()[:16]
            if not alias or alias in self._aliases:
                raise GeminiConnectionError("tool_schema_unsupported", recoverable=False)
            try:
                Draft202012Validator.check_schema(spec["parameters"])
            except SchemaError:
                raise GeminiConnectionError("tool_schema_unsupported", recoverable=False) from None
            if spec["parameters"].get("type") != "object":
                raise GeminiConnectionError("tool_schema_unsupported", recoverable=False)
            self._aliases[alias] = name
            self._validators[name] = Draft202012Validator(spec["parameters"])
            declaration: dict[str, object] = {
                "name": alias,
                "description": spec["description"],
                "parametersJsonSchema": spec["parameters"],
            }
            if name in tools and not tools[name].needs_response:
                self._silent_tools.add(name)
                declaration["behavior"] = "NON_BLOCKING"
            declarations.append(declaration)
        return declarations

    async def _send(self, payload: dict[str, object]) -> None:
        if self.connection is None or not self._owns_connection():
            raise GeminiConnectionError("connection_lost")
        connection = self.connection

        async def write() -> None:
            async with self._send_lock:
                if not self._owns_connection():
                    raise GeminiConnectionError("connection_lost")
                await connection.send(json.dumps(payload))

        try:
            await self._bounded_send(write())
        except TimeoutError:
            raise GeminiConnectionError("send_timeout") from None

    async def start_up(self) -> None:
        """Run one acknowledged Live connection; the stream owner schedules recovery."""
        api_key = config.GEMINI_API_KEY if self._api_key is None else self._api_key
        if not api_key:
            raise GeminiConnectionError("missing_gemini_key", recoverable=False)
        if not re.fullmatch(r"(?:models/)?[a-zA-Z0-9._-]+", config.GEMINI_MODEL):
            raise GeminiConnectionError("invalid_gemini_model", recoverable=False)
        voice = self.get_current_voice()
        self._closed = False
        self._generation = self.session_state.generation
        self._logical_session_id = self.session_state.logical_session_id
        self._aliases.clear()
        self._validators.clear()
        declarations = self._declarations()
        setup: dict[str, object] = {
            "model": "models/" + config.GEMINI_MODEL.removeprefix("models/"),
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}},
                },
            },
            "systemInstruction": {"parts": [{"text": get_session_instructions(self.instance_path)}]},
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "contextWindowCompression": {"slidingWindow": {}},
            "sessionResumption": {},
        }
        if declarations:
            setup["tools"] = [{"functionDeclarations": declarations}]
        handle = self.session_state.resumption_handle if self.session_state.resumable else None
        if handle:
            setup["sessionResumption"] = {"handle": handle}
        elif self.session_state.context_state == "unavailable":
            await self._fresh_context()
        deadline = time.monotonic() + SETUP_TIMEOUT_S
        fallback = False
        try:
            while self._owns_connection():
                try:
                    async with asyncio.timeout(max(0, deadline - time.monotonic())):
                        socket_context = connect(
                            GEMINI_LIVE_URL,
                            additional_headers={"x-goog-api-key": api_key},
                            open_timeout=max(0, deadline - time.monotonic()),
                            close_timeout=CLOSE_TIMEOUT_S,
                            max_size=16 * 1024 * 1024,
                            logger=transport_logger,
                        )
                        self.connection = await socket_context.__aenter__()
                        await self._send({"setup": setup})
                        while True:
                            envelope = _decode_message(await self.connection.recv())
                            if "error" in envelope:
                                self._raise_remote_error(_object(envelope["error"]))
                            if "setupComplete" in envelope:
                                if not isinstance(envelope["setupComplete"], dict):
                                    raise GeminiConnectionError("connection_lost")
                                break
                    if not self._owns_connection():
                        return
                    self._ready = True
                    self.session_state.context_state = "resumed" if handle else "new"
                    output_rate = self.deps.reachy_mini.media.get_output_audio_samplerate()
                    self._output_rate = output_rate if isinstance(output_rate, int) and output_rate > 0 else 24000
                    self._output_resampler = AudioResampler(24000, self._output_rate)
                    if config.LOCAL_VAD_ENABLED:
                        try:
                            self._local_vad = await asyncio.to_thread(SileroVAD)
                        except (OSError, RuntimeError, ValueError) as error:
                            logger.warning("Local VAD unavailable: %s", type(error).__name__)
                            self.paced_playback = False
                    self.tool_manager.start_up(tool_callbacks=[self._handle_tool_result])
                    if not handle:
                        await self.say(get_session_greeting_prompt())
                    while self._owns_connection():
                        timeout = max(0, self._barrier_deadline - time.monotonic()) if self._draining else None
                        try:
                            async with asyncio.timeout(timeout):
                                envelope = _decode_message(await self.connection.recv())
                        except TimeoutError:
                            await self._fresh_context()
                            raise GeminiConnectionError("resume_unavailable") from None
                        if self._owns_connection():
                            await self._handle_message(envelope)
                    return
                except (GeminiConnectionError, ConnectionClosed) as error:
                    # A rejected checkpoint gets one fresh attempt inside the original setup budget.
                    if isinstance(error, ConnectionClosed):
                        close_reason = error.rcvd.reason.lower() if error.rcvd is not None else ""
                        rejected_resume = (
                            error.rcvd is not None
                            and error.rcvd.code in (1007, 1008)
                            and any(word in close_reason for word in ("resum", "invalid handle", "session handle"))
                        )
                    else:
                        rejected_resume = error.reason == "resume_unavailable"
                    if not self._ready and handle and not fallback and rejected_resume and time.monotonic() < deadline:
                        await self._close_socket()
                        await self._fresh_context()
                        setup["sessionResumption"] = {}
                        handle = None
                        fallback = True
                        continue
                    if isinstance(error, GeminiConnectionError):
                        raise
                    code = error.rcvd.code if error.rcvd is not None else 1006
                    recoverable = code in (1000, 1001, 1006, 1011, 1012, 1013, 1014)
                    raise GeminiConnectionError(
                        "connection_lost" if recoverable else "access_unavailable",
                        recoverable=recoverable,
                    ) from None
        except TimeoutError:
            raise GeminiConnectionError("setup_timeout") from None
        except InvalidStatus as error:
            self._raise_remote_error({"code": error.response.status_code})
        except json.JSONDecodeError:
            raise GeminiConnectionError("connection_lost") from None
        finally:
            self._ready = False
            if self._logical_session_id == self.session_state.logical_session_id:
                for invocation in self.session_state.invocations.values():
                    if invocation.status in ("received", "running"):
                        invocation.status = "uncertain"
            await self.tool_manager.shutdown()
            await self._close_socket()

    @staticmethod
    def _raise_remote_error(error: dict[str, object]) -> None:
        code = error.get("code")
        message = str(error.get("message", "")).lower()
        reason = {
            400: "invalid_gemini_model",
            401: "authentication_failed",
            403: "access_unavailable",
            404: "access_unavailable",
        }.get(code if isinstance(code, int) else 0, "connection_lost")
        if code == 429:
            if any(
                word in message
                for word in (
                    "billing",
                    "daily",
                    "per day",
                    "perday",
                    "quota exhausted",
                    "insufficient_quota",
                    "budget",
                )
            ):
                reason = "quota_exceeded"
        if code == 400:
            if any(word in message for word in ("api key", "api_key")):
                reason = "authentication_failed"
            elif any(word in message for word in ("tool", "function", "schema")):
                reason = "tool_schema_unsupported"
            elif any(word in message for word in ("resum", "invalid handle", "session handle")):
                reason = "resume_unavailable"
        raise GeminiConnectionError(reason, recoverable=reason == "connection_lost")

    async def _handle_message(self, envelope: dict[str, object]) -> None:
        if not self._owns_connection():
            return
        if "error" in envelope:
            self._raise_remote_error(_object(envelope["error"]))
        update = _object(envelope.get("sessionResumptionUpdate"))
        if update:
            handle = update.get("newHandle")
            self.session_state.resumable = update.get("resumable") is True and isinstance(handle, str) and bool(handle)
            self.session_state.resumption_handle = (
                handle if self.session_state.resumable and isinstance(handle, str) else None
            )
        if "goAway" in envelope:
            self._mark_activity("reconnecting")
            raise GeminiConnectionError("connection_lost")
        cancellations = _object(envelope.get("toolCallCancellation")).get("ids")
        if isinstance(cancellations, list):
            for call_id in cancellations:
                if isinstance(call_id, str) and call_id in self.session_state.invocations:
                    if self.session_state.invocations[call_id].status == "running":
                        self._mark_activity("uncertain_action")
                    self.session_state.invocations[call_id].status = "cancelled"
                    tool_id = self._tool_ids.get(call_id)
                    if tool_id:
                        await self.tool_manager.cancel_tool(tool_id)
        content = _object(envelope.get("serverContent"))
        if "serverContent" in envelope and not isinstance(envelope["serverContent"], dict):
            raise GeminiConnectionError("connection_lost")
        incoming = _object(content.get("inputTranscription")).get("text")
        if isinstance(incoming, str) and incoming:
            self._turn_active = True
            self._input_text += incoming
            self._emit_transcript("user", self._input_text, False)
            self._mark_activity("user_transcription_delta")
        if content.get("interrupted") is True:
            self._exchange_has_output = False
            self._barrier_deadline = time.monotonic() + TURN_BOUNDARY_TIMEOUT_S
            self._draining = True
            await self._flush_playback()
            self._assistant_text = ""
            if self._output_resampler is not None:
                self._output_resampler.reset()
            if self.transcript_interrupted is not None:
                self.transcript_interrupted()
        if self._draining:
            if content.get("turnComplete") is True:
                self._draining = False
                self._turn_active = False
                if self._input_text:
                    self._emit_transcript("user", self._input_text, True)
                    self._input_text = ""
            return
        epoch = self.playback_epoch
        calls = _object(envelope.get("toolCall")).get("functionCalls")
        if "toolCall" in envelope and not isinstance(calls, list):
            raise GeminiConnectionError("connection_lost")
        if isinstance(calls, list):
            for call in calls:
                await self._tool_call(_object(call))
        parts = _object(content.get("modelTurn")).get("parts")
        if "modelTurn" in content and not isinstance(parts, list):
            raise GeminiConnectionError("connection_lost")
        if isinstance(parts, list):
            for part in parts:
                part_fields = _object(part)
                if "inlineData" in part_fields and not isinstance(part_fields["inlineData"], dict):
                    raise GeminiConnectionError("connection_lost")
                inline = _object(part_fields.get("inlineData"))
                encoded = inline.get("data")
                if inline and not isinstance(encoded, str):
                    raise GeminiConnectionError("connection_lost")
                if inline and inline.get("mimeType") != "audio/pcm;rate=24000":
                    raise GeminiConnectionError("connection_lost")
                if isinstance(encoded, str) and inline.get("mimeType") == "audio/pcm;rate=24000":
                    try:
                        samples = np.frombuffer(base64.b64decode(encoded, validate=True), dtype="<i2")
                    except (ValueError, TypeError):
                        raise GeminiConnectionError("connection_lost") from None
                    if self._output_resampler is not None:
                        await self._queue_audio(self._output_resampler.process(samples), epoch)
        transcript = _object(content.get("outputTranscription")).get("text")
        if isinstance(transcript, str):
            self._turn_active = True
            self._exchange_has_output = self._exchange_has_output or bool(transcript)
            self._assistant_text += transcript
            self._emit_transcript("assistant", self._assistant_text, False)
        if content.get("turnComplete") is True:
            if self._output_resampler is not None:
                await self._queue_audio(self._output_resampler.process(np.empty(0, dtype=np.int16), final=True), epoch)
            self._turn_active = content.get("interactionStatus") == "IN_PROGRESS"
            self.deps.movement_manager.set_speaking(False)
            for role, text in (("user", self._input_text), ("assistant", self._assistant_text)):
                if text:
                    self._emit_transcript(role, text, True)
                    await self.output_queue.put(AdditionalOutputs({"role": role, "content": text}))
            self._input_text = self._assistant_text = ""
            self._mark_activity("response_created" if self._turn_active else "assistant_transcript_done")
            if not self._turn_active and self._exchange_has_output:
                self.notify_exchange_completed()
                self._exchange_has_output = False

    async def _queue_audio(self, samples: np.ndarray[tuple[int, ...], np.dtype[np.int16]], epoch: int) -> None:
        if samples.size and self._owns_connection() and epoch == self.playback_epoch:
            self._turn_active = True
            self._exchange_has_output = True
            self._audio_response_id = "gemini-turn"
            self.deps.movement_manager.set_speaking(True)
            frame = samples.reshape(1, -1)
            self.playback_frame_epochs[id(frame)] = epoch
            await self.output_queue.put((self._output_rate, frame))
            if self.paced_playback:
                self.playback_pending_frames += 1
            self._mark_activity("assistant_audio_delta")

    async def _tool_call(self, call: dict[str, object]) -> None:
        call_id, alias = call.get("id"), call.get("name")
        if not isinstance(call_id, str) or not isinstance(alias, str) or not self._owns_connection():
            raise GeminiConnectionError("connection_lost")
        name = self._aliases.get(alias)
        if name is None:
            await self._function_response(call_id, alias, {"error": "Tool is not enabled"})
            return
        invocation = self.session_state.invocations.get(call_id)
        if invocation is not None:
            if invocation.tool_name != name:
                await self._function_response(call_id, alias, {"error": "Call ID already used for a different tool"})
                return
            result = invocation.result if invocation.status == "completed" else None
            await self._function_response(
                call_id, alias, result or {"error": "Previous action outcome is uncertain; not repeated"}
            )
            return
        invocation = ToolInvocation(name, generation=self._generation, response_epoch=self.playback_epoch)
        self.session_state.invocations[call_id] = invocation
        arguments = call.get("args", {})
        if not isinstance(arguments, dict) or not self._validators[name].is_valid(arguments):
            invocation.result = {"error": "Invalid tool arguments"}
            invocation.status = "completed"
            await self._function_response(call_id, alias, invocation.result)
            return
        invocation.status = "running"
        self._mark_activity("tool_call_received")
        tool = await self.tool_manager.start_tool(
            call_id,
            ToolCallRoutine(tool_name=name, args_json_str=json.dumps(arguments), deps=self.deps),
            is_idle_tool_call=False,
        )
        self._tool_ids[call_id] = tool.tool_id

    async def _handle_tool_result(self, notification: ToolNotification) -> None:
        invocation = self.session_state.invocations.get(notification.id)
        if not self._owns_connection() or invocation is None or invocation.status != "running":
            return
        uncertain = notification.tool_name == "volume_control" and notification.error == VOLUME_CHANGE_UNCERTAIN
        result: dict[str, object] = (
            _object(notification.result)
            if notification.result is not None
            else {"error": "Tool failed or was cancelled"}
        )
        if uncertain:
            result = {"error": VOLUME_CHANGE_UNCERTAIN, "uncertain": True}
        image = result.pop("b64_im", None)
        if isinstance(image, str):
            result["snapshot"] = "captured"
        invocation.result = result
        invocation.status = "uncertain" if uncertain else "completed"
        if uncertain and not invocation.uncertainty_reported:
            invocation.uncertainty_reported = True
            self._mark_activity("uncertain_action")
        alias = next(alias for alias, name in self._aliases.items() if name == invocation.tool_name)
        await self._function_response(notification.id, alias, result)
        if isinstance(image, str) and self.deps.camera_enabled and self._owns_connection():
            await self._send({"realtimeInput": {"video": {"mimeType": "image/jpeg", "data": image}}})
        self._mark_activity("tool_result_ready")
        if invocation.tool_name in ("remember", "forget") and "error" not in result:
            await self._flush_playback()
            await self._fresh_context()
            self._closed = True
            self._ready = False
            await self._close_socket()

    async def _function_response(self, call_id: str, alias: str, result: dict[str, object]) -> None:
        response: dict[str, object] = {"id": call_id, "name": alias, "response": result}
        if self._aliases.get(alias) in self._silent_tools:
            response["scheduling"] = "SILENT"
        await self._send({"toolResponse": {"functionResponses": [response]}})

    async def receive(self, frame: AudioFrame) -> None:
        """Send live mono PCM without retaining input while disconnected."""
        if not self._is_connected():
            return
        rate, samples = frame
        samples = audio_to_int16(samples)
        if self._input_resampler is None or self._input_rate != rate:
            self._input_rate = rate
            self._input_resampler = AudioResampler(rate, 16000)
        mono = (
            samples.reshape(-1)
            if samples.ndim < 2
            else samples.mean(axis=0 if samples.shape[0] < samples.shape[1] else 1).astype(np.int16)
        )
        converted = self._input_resampler.process(mono)
        if converted.size:
            try:
                await self._send(
                    {
                        "realtimeInput": {
                            "audio": {
                                "mimeType": "audio/pcm;rate=16000",
                                "data": base64.b64encode(converted.astype("<i2").tobytes()).decode(),
                            }
                        }
                    }
                )
            except (ConnectionError, ConnectionClosed):
                logger.debug("Dropping microphone frame: Gemini transport unavailable")
                return
        self._process_local_audio(rate, mono)

    async def say(self, text: str) -> None:
        """Request spoken output for an injected instruction."""
        if not self._is_connected():
            raise GeminiConnectionError("connection_lost")
        await self._send(
            {"clientContent": {"turns": [{"role": "user", "parts": [{"text": text}]}], "turnComplete": True}}
        )

    async def _fresh_context(self) -> None:
        if self.session_state.mark_uncertain_actions():
            self._mark_activity("uncertain_action")
        self.session_state.fresh("gemini", self.session_state.revision)
        self._logical_session_id = self.session_state.logical_session_id
        self._generation = self.session_state.generation
        self._mark_activity("fresh_context")

    async def interrupt(self) -> None:
        """Flush uncorrelated app interruption and reconnect with fresh context."""
        if not self._owns_connection():
            return
        await self._flush_playback()
        if self.transcript_interrupted is not None:
            self.transcript_interrupted()
        await self._fresh_context()
        await self.shutdown()

    async def apply_personality(self, profile: str | None) -> str:
        """Select a personality and retire the previous Gemini context."""
        set_custom_profile(profile)
        await self.interrupt()
        return "人格已選取，正在開始新對話。"

    async def refresh_instructions(self) -> bool:
        """Retire Gemini context so changed saved memories enter the next setup."""
        await self.interrupt()
        return False

    async def change_voice(self, voice: str) -> str:
        """Select a compatible Gemini voice for a fresh conversation."""
        if voice not in GEMINI_AVAILABLE_VOICES:
            raise ValueError("invalid_gemini_voice")
        config.GEMINI_VOICE_OVERRIDE = voice
        await self.interrupt()
        return "聲音已選取，正在開始新對話。"

    async def _close_socket(self) -> None:
        connection, self.connection = self.connection, None
        if connection is not None:
            closing = asyncio.create_task(connection.close())
            try:
                completed, _pending = await asyncio.wait({closing}, timeout=CLOSE_TIMEOUT_S)
                if completed:
                    await closing
                else:
                    logger.warning("Gemini connection cleanup exceeded its deadline")
            except ConnectionClosed:
                logger.warning("Gemini connection cleanup did not complete")
            finally:
                if not closing.done():
                    connection.transport.abort()
                    closing.cancel()
                    closing.add_done_callback(self._consume_send)

    async def shutdown(self) -> None:
        """Release transport ownership while preserving the owner's resume ledger."""
        self._closed = True
        self._ready = False
        self._reset_listening()
        if self._logical_session_id == self.session_state.logical_session_id:
            for invocation in self.session_state.invocations.values():
                if invocation.status in ("received", "running"):
                    invocation.status = "uncertain"
        await self.tool_manager.shutdown()
        await self._close_socket()


async def validate_gemini_candidate(candidate: str, model: str, voice: str) -> None:
    """Check Live setup eligibility without sending conversation content or starting media."""
    if not candidate.strip():
        raise GeminiConnectionError("invalid_input", recoverable=False)
    if not re.fullmatch(r"(?:models/)?[a-zA-Z0-9._-]+", model):
        raise GeminiConnectionError("invalid_gemini_model", recoverable=False)
    if voice not in GEMINI_AVAILABLE_VOICES:
        raise GeminiConnectionError("invalid_gemini_voice", recoverable=False)
    setup = {
        "model": "models/" + model.removeprefix("models/"),
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    try:
        async with asyncio.timeout(SETUP_TIMEOUT_S):
            async with connect(
                GEMINI_LIVE_URL,
                additional_headers={"x-goog-api-key": candidate},
                open_timeout=SETUP_TIMEOUT_S,
                close_timeout=CLOSE_TIMEOUT_S,
                max_size=1024 * 1024,
                logger=transport_logger,
            ) as connection:
                await connection.send(json.dumps({"setup": setup}))
                while True:
                    envelope = _decode_message(await connection.recv())
                    if "error" in envelope:
                        remote = _object(envelope["error"])
                        code = remote.get("code")
                        if code in (403, 404):
                            raise GeminiConnectionError("model_not_available", recoverable=False)
                        if code == 429:
                            raise GeminiConnectionError("quota_exceeded", recoverable=False)
                        GeminiRealtimeHandler._raise_remote_error(remote)
                    if isinstance(envelope.get("setupComplete"), dict):
                        return
    except InvalidStatus as error:
        reason = {
            400: "invalid_gemini_model",
            401: "authentication_failed",
            403: "model_not_available",
            404: "model_not_available",
            429: "quota_exceeded",
        }.get(error.response.status_code, "service_unavailable")
        raise GeminiConnectionError(reason, recoverable=False) from None
    except GeminiConnectionError as error:
        if error.reason == "connection_lost":
            raise GeminiConnectionError("service_unavailable") from None
        raise
    except TimeoutError:
        raise GeminiConnectionError("validation_timeout") from None
    except ConnectionClosed as error:
        received = error.rcvd
        if received is not None and received.code in (1007, 1008):
            if any(fragment in received.reason.lower() for fragment in ("api key not valid", "api_key_invalid")):
                raise GeminiConnectionError("authentication_failed", recoverable=False) from None
        raise GeminiConnectionError("service_unavailable") from None
    except (OSError, json.JSONDecodeError):
        raise GeminiConnectionError("service_unavailable") from None
