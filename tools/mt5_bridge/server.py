from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from tools.mt5_bridge.mt5_client import MT5Client


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


def _redact_payload(payload):
    if isinstance(payload, dict):
        return {key: ("[REDACTED]" if str(key).lower() in {"login", "password", "server"} else _redact_payload(value)) for key, value in payload.items()}
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

