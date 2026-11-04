import os
import sys
import json
import asyncio
import argparse
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from collections.abc import Callable, Awaitable

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse


os.environ["REACHY_MINI_SKIP_DOTENV"] = "1"
os.environ["GEMINI_API_KEY"] = ""
os.environ["HF_TOKEN"] = ""
os.environ["HF_HOME"] = str(Path(__file__).resolve().parents[2] / "cache" / "inline-fixture-hf")
os.environ["REACHY_MINI_CUSTOM_PROFILE"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY"] = str(Path(__file__).resolve().parents[2] / "profiles")
os.environ["REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY"] = str(
    Path(__file__).resolve().parents[2] / "cache" / "inline-no-tools"
)
os.environ["REACHY_MINI_INSTANCE_PATH"] = str(
    Path(__file__).resolve().parents[2] / "cache" / f"inline-scope-{os.getpid()}"
)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

from test_gemini_credentials import FakeVault

from reachy_mini_conversation_app import console
from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.gemini_realtime import GeminiConnectionError
from reachy_mini_conversation_app.gemini_credentials import GeminiCredentials


ROOT = Path(__file__).resolve().parents[2]


class SettingsFixture:
    """Serve isolated key settings with fake storage and no conversation startup."""

    def __init__(self, scope: Path) -> None:
        """Create fake dependencies without opening a native store or robot."""
        self.scope = scope
        self.vault = FakeVault()
        self.store: GeminiCredentials | None = None
        self.delay = 0.0
        self.requests: list[str] = []
        self.bootstrap_failure = False
        self.bootstrap_delay = 0.0
        self.sequence = 0
        self.environment = ""
        self.app = FastAPI()
        self.handler = MagicMock(connection=None, shutdown=AsyncMock())
        config.CONVERSATION_BACKEND = "huggingface"
        config.GEMINI_MODEL = "offline-fixture"
        config.GEMINI_VOICE_OVERRIDE = "Kore"
        config.CAMERA_ENABLED = False
        config.MEMORY_ENABLED = False
        self.reset("none")
        self.stream = console.LocalStream(
            self.handler, MagicMock(), settings_app=self.app, instance_path=str(scope), credentials=self.store
        )
        console.validate_gemini_candidate = self.validate
        self.stream._init_settings_ui_if_needed()
        self.stream._set_backend_connection_state("connected")
        self.app.add_api_route("/fixture/control", self.control, methods=["POST"])
        self.app.add_api_route("/fixture/status", self.status, methods=["GET"])
        self.app.middleware("http")(self.observe)

    def reset(self, source: str) -> None:
        """Replace only this fixture's fake scope and selected environment source."""
        if self.store is not None:
            self.store.close()
        self.sequence += 1
        self.vault = FakeVault()
        environment = "offline-environment" if source in ("environment", "both") else ""
        self.environment = environment
        self.store = GeminiCredentials(self.scope / str(self.sequence), environment, vault_factory=lambda: self.vault)
        self.store.initialize()
        if source in ("managed", "both"):
            revision = self.store.begin(self.store.revision)
            self.store.save("offline-first", revision)

    async def validate(self, candidate: str, model: str, voice: str) -> None:
        """Accept only named non-secret fixtures without a network call."""
        await asyncio.sleep(self.delay)
        if candidate == "offline-invalid":
            raise GeminiConnectionError("authentication_failed", recoverable=False)
        if candidate not in ("offline-first", "offline-second"):
            raise GeminiConnectionError("invalid_params", recoverable=False)

    async def observe(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Record methods only and label the fake page without retaining request bodies."""
        if request.url.path == "/api/gemini-credential":
            self.requests.append(request.method)
            if request.method == "GET":
                await asyncio.sleep(self.bootstrap_delay)
            if request.method == "GET" and self.bootstrap_failure:
                return HTMLResponse("Unavailable fixture", status_code=503)
        if request.url.path == "/":
            markup = (ROOT / "src/reachy_mini_conversation_app/static/index.html").read_text(encoding="utf-8")
            markup = markup.replace(
                "<body>",
                '<body><p role="note">離線模擬：只輸入 offline-first／offline-second／offline-invalid，不要輸入真實金鑰。</p>',
            )
            return HTMLResponse(markup, headers={"Cache-Control": "no-store"})
        if request.url.path in (
            "/fixture/wrapper",
            "/fixture/grandparent",
            "/fixture/opaque",
            "/fixture/hidden-parent",
        ):
            target = "/fixture/wrapper" if request.url.path.endswith(("grandparent", "opaque")) else "/#/settings"
            attributes = (
                'sandbox="allow-scripts"' if request.url.path.endswith("opaque") else 'referrerpolicy="no-referrer"'
            )
            if request.url.path.endswith(("wrapper", "grandparent")):
                attributes = ""
            return HTMLResponse(f'<iframe {attributes} src="http://127.0.0.1:{request.url.port}{target}"></iframe>')
        return await call_next(request)

    async def control(self, request: Request) -> dict[str, object]:
        """Configure fake states or restart only the fake credential owner."""
        payload = await request.json()
        scene = payload.get("scene", "none")
        if scene == "restart":
            assert self.store is not None
            scope, environment = self.store.scope, self.environment
            self.store.close()
            self.store = GeminiCredentials(scope, environment, vault_factory=lambda: self.vault)
            self.store.initialize()
        else:
            assert scene in ("none", "environment", "managed", "both")
            self.reset(scene)
        self.stream._credentials = self.store
        self.stream._credential_hold = False
        self.stream._restart_requested.clear()
        self.delay = min(max(float(payload.get("delay", 0)), 0), 3)
        self.vault.failure = payload.get("failure")
        self.bootstrap_failure = payload.get("bootstrap_failure", False)
        self.bootstrap_delay = min(max(float(payload.get("bootstrap_delay", 0)), 0), 3)
        config.CONVERSATION_BACKEND = "gemini" if payload.get("provider") == "gemini" else "huggingface"
        self.stream._set_backend_connection_state(payload.get("connection", "connected"))
        self.requests.clear()
        return self.status()

    def status(self) -> dict[str, object]:
        """Expose fake counters and safe state without fake credential values."""
        assert self.store is not None
        return {
            **self.stream._credential_status(),
            "requests": list(self.requests),
            "entries": len(self.vault.entries),
            "fake_only": True,
        }


def main() -> None:
    """Run only the isolated settings fixture on loopback."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7864)
    args = parser.parse_args()
    cache = ROOT / "cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="inline-key-", dir=cache) as directory:
        fixture = SettingsFixture(Path(directory))
        loop = asyncio.SelectorEventLoop()
        server = uvicorn.Server(
            uvicorn.Config(fixture.app, host="127.0.0.1", port=args.port, log_level="warning", proxy_headers=False)
        )

        @fixture.app.post("/fixture/finish")
        def finish() -> dict[str, bool]:
            """Stop this fake server so its owner can release temporary storage."""
            server.should_exit = True
            return {"stopping": True}

        def forbid_network(event: str, arguments: tuple[object, ...]) -> None:
            if event == "socket.connect":
                raise RuntimeError("Outbound sockets are disabled in the offline fixture")

        sys.addaudithook(forbid_network)
        print(json.dumps({"fixture": f"http://127.0.0.1:{args.port}/#/settings", "fake_only": True}), flush=True)
        try:
            loop.run_until_complete(server.serve())
        finally:
            assert fixture.store is not None
            fixture.store.close()
            loop.close()


if __name__ == "__main__":
    main()
