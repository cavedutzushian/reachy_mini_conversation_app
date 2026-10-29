import json
import logging
import threading
from types import SimpleNamespace
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import MagicMock

import httpx
import pytest

from reachy_mini_conversation_app import daemon_api


def test_get_request_has_no_body_and_decodes_json(daemon_http_handler: MagicMock) -> None:
    """A GET carries no payload and retains the configured timeout."""
    daemon_http_handler.return_value = httpx.Response(200, json={"volume": 42})
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    assert daemon_api.daemon_request(robot, "/api/volume/current") == {"volume": 42}
    request = daemon_http_handler.call_args.args[0]
    assert str(request.url) == "http://192.168.1.42:8000/api/volume/current"
    assert request.method == "GET"
    assert request.content == b""
    assert set(request.extensions["timeout"].values()) == {daemon_api.DEFAULT_TIMEOUT_S}
    assert request.headers.get("Connection", "").lower() != "close"


def test_response_is_read_before_daemon_connection_closes() -> None:
    """Read a daemon response without requesting its problematic immediate socket close."""

    class DaemonHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            if self.headers.get("Connection", "").lower() == "close":
                self.close_connection = True
                return
            body = b'{"robot_name":"reachy_mini"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            logging.getLogger(__name__).debug(format, *args)

    server = HTTPServer(("127.0.0.1", 0), DaemonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    robot = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1", port=server.server_port))
    try:
        assert daemon_api.daemon_request(robot, "/api/daemon/status") == {"robot_name": "reachy_mini"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_post_sends_json_body_and_content_type(daemon_http_handler: MagicMock) -> None:
    """FastAPI receives a JSON payload with its content type."""
    daemon_http_handler.return_value = httpx.Response(200, json={"volume": 70})
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    result = daemon_api.daemon_request(robot, "/api/volume/set", method="POST", payload={"volume": 70})

    assert result == {"volume": 70}
    request = daemon_http_handler.call_args.args[0]
    assert request.method == "POST"
    assert json.loads(request.content) == {"volume": 70}
    assert request.headers["Content-Type"] == "application/json"


def test_none_body_decodes_to_none(daemon_http_handler: MagicMock) -> None:
    """The daemon stop route's JSON null remains a successful response."""
    daemon_http_handler.return_value = httpx.Response(200, content=b"null")
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    assert daemon_api.daemon_request(robot, "/api/apps/stop-current-app", method="POST") is None


def test_http_error_is_wrapped(daemon_http_handler: MagicMock) -> None:
    """An HTTP failure retains its status code."""
    daemon_http_handler.return_value = httpx.Response(503)
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    with pytest.raises(daemon_api.DaemonApiError, match="503") as raised:
        daemon_api.daemon_request(robot, "/api/volume/current")
    assert raised.value.status_code == 503


def test_http_error_preserves_daemon_detail(daemon_http_handler: MagicMock) -> None:
    """Callers can distinguish daemon errors sharing an HTTP status."""
    daemon_http_handler.return_value = httpx.Response(400, json={"detail": "Stop cleanup failed"})
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    with pytest.raises(daemon_api.DaemonApiError, match="Stop cleanup failed") as raised:
        daemon_api.daemon_request(robot, "/api/apps/stop-current-app", method="POST")

    assert raised.value.status_code == 400
    assert raised.value.detail == "Stop cleanup failed"


@pytest.mark.parametrize("body", [b"<html>Unavailable</html>", b"\xff", b"null", b'{"detail":42}'])
def test_http_error_without_string_detail_remains_wrapped(daemon_http_handler: MagicMock, body: bytes) -> None:
    """Unusable error bodies retain the HTTP failure instead of escaping."""
    daemon_http_handler.return_value = httpx.Response(503, content=body)
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    with pytest.raises(daemon_api.DaemonApiError, match="503") as raised:
        daemon_api.daemon_request(robot, "/api/volume/current")

    assert raised.value.status_code == 503
    assert raised.value.detail is None


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout])
def test_transport_error_is_wrapped(daemon_http_handler: MagicMock, error_type: type[httpx.RequestError]) -> None:
    """Transport failures and deadlines remain daemon errors."""
    daemon_http_handler.side_effect = error_type("connection unavailable")
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    with pytest.raises(daemon_api.DaemonApiError):
        daemon_api.daemon_request(robot, "/api/volume/current")


@pytest.mark.parametrize("body", [b"<html>nope</html>", b"\xff"])
def test_invalid_json_is_wrapped(daemon_http_handler: MagicMock, body: bytes) -> None:
    """Malformed JSON or encoding cannot escape into the conversation."""
    daemon_http_handler.return_value = httpx.Response(200, content=body)
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    with pytest.raises(daemon_api.DaemonApiError, match="invalid JSON"):
        daemon_api.daemon_request(robot, "/api/volume/current")


def test_failed_action_is_not_retried(daemon_http_handler: MagicMock) -> None:
    """An uncertain POST result never causes an action to be sent twice."""
    daemon_http_handler.side_effect = httpx.ReadError("connection reset after send")
    robot = SimpleNamespace(client=SimpleNamespace(host="192.168.1.42", port=8000))

    with pytest.raises(daemon_api.DaemonApiError):
        daemon_api.daemon_request(robot, "/api/volume/set", method="POST", payload={"volume": 40})

    daemon_http_handler.assert_called_once()
    assert daemon_http_handler.call_args.args[0].method == "POST"
