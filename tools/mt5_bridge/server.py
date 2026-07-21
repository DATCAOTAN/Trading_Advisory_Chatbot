from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from tools.mt5_bridge.execution import ControlledMT5ExecutionService
from tools.mt5_bridge.mt5_client import MT5Client


load_dotenv()
CLIENT = MT5Client()


class MT5BridgeHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        try:
            if parsed.path == "/health":
                payload = CLIENT.health()
            elif parsed.path == "/account":
                payload = CLIENT.account_info()
            elif parsed.path == "/symbols":
                payload = CLIENT.symbols()
            elif parsed.path == "/tick":
                payload = CLIENT.tick(params.get("symbol", "XAUUSD"))
            elif parsed.path == "/ohlcv":
                payload = CLIENT.ohlcv(params.get("symbol", "XAUUSD"), params.get("timeframe", "M15"), int(params.get("count", "300")))
            elif parsed.path == "/positions":
                payload = CLIENT.positions(params.get("symbol") or None)
            else:
                self._send({"status": "NOT_FOUND", "message": "unknown endpoint"}, status=404)
                return
            self._send(payload)
        except Exception as exc:
            self._send({"status": "UNAVAILABLE", "message": f"bridge error: {type(exc).__name__}"}, status=503)

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/execution/write-skeleton/check":
                self._discard_request_body()
                self._send(_blocked_write_skeleton_response())
                return
            if parsed.path == "/execution/controlled-submit":
                payload = self._read_json_body()
                token = self.headers.get("X-MT5-Bridge-Execution-Token", "")
                response, status = ControlledMT5ExecutionService(CLIENT).handle(payload, token)
                self._send(response, status=status)
                return
            self._send({"status": "NOT_FOUND", "message": "unknown endpoint"}, status=404)
        except Exception as exc:
            self._send({"status": "UNAVAILABLE", "message": f"bridge error: {type(exc).__name__}"}, status=503)

    def log_message(self, fmt, *args):  # noqa: A003
        safe = str(fmt).replace("%s", "{}")
        try:
            print("[MT5Bridge] " + safe.format(*args))
        except Exception:
            print("[MT5Bridge] request")

    def _send(self, payload, status: int = 200):
        body = json.dumps(_redact_payload(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _discard_request_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            length = 0
        if length > 0:
            self.rfile.read(length)

    def _read_json_body(self, maximum_bytes: int = 65536):
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if length <= 0 or length > maximum_bytes:
            raise ValueError("invalid request size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid request payload")
        return payload


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _blocked_write_skeleton_response():
    _ = (
        _env_bool("MT5_BRIDGE_WRITE_SKELETON_ENABLED", True),
        _env_bool("MT5_BRIDGE_WRITE_SKELETON_HARD_BLOCK", True),
        _env_bool("MT5_BRIDGE_ORDER_SEND_ENABLED", False),
        _env_bool("MT5_BRIDGE_LIVE_EXECUTION_ENABLED", False),
    )
    return {
        "status": "BLOCKED",
        "endpoint": "/execution/write-skeleton/check",
        "write_skeleton_available": True,
        "live_execution_allowed": False,
        "order_send_allowed": False,
        "execution_allowed": False,
        "hard_live_block_required": True,
        "reason": "MT5 bridge write endpoint skeleton is disabled by design",
        "order_sent": False,
        "ticket": None,
        "deal": None,
        "metadata_redacted": True,
    }


def _redact_payload(payload):
    if isinstance(payload, dict):
        protected_keys = {
            "login", "password", "server", "auth_token", "human_confirmation_phrase",
            "approved_semantic_parameters", "raw_request", "protected_result",
        }
        return {
            key: ("[REDACTED]" if str(key).lower() in protected_keys else _redact_payload(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_redact_payload(item) for item in payload]
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="Host-side MT5 bridge service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), MT5BridgeHandler)
    print(f"[MT5Bridge] listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        CLIENT.close()
        server.server_close()


if __name__ == "__main__":
    main()
