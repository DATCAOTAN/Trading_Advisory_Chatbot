# Host-Side MT5 Bridge

Run this service on the Windows host where MetaTrader 5 terminal is installed and already logged in by the user.

```powershell
.\venv\Scripts\python.exe -m tools.mt5_bridge.server
```

Default bind address:

```text
http://127.0.0.1:8765
```

Docker app configuration:

```text
MARKET_DATA_PROVIDER=mt5_bridge
MT5_BRIDGE_URL=http://host.docker.internal:8765
```

Native local app alternative:

```text
MT5_BRIDGE_URL=http://127.0.0.1:8765
```

Endpoints:

- `GET /health`
- `GET /account`
- `GET /symbols`
- `GET /tick?symbol=XAUUSD`
- `GET /ohlcv?symbol=XAUUSD&timeframe=M15&count=300`
- `GET /positions?symbol=XAUUSD`
- `POST /execution/write-skeleton/check` (always blocked)
- `POST /execution/lifecycle-snapshot` (authenticated, read-only)
- `POST /execution/reconcile` (authenticated, read-only)
- `POST /execution/controlled-submit` (authenticated, disabled by default)
- `POST /execution/controlled-manage` (authenticated, disabled by default)

Authenticated POST endpoints use `X-MT5-Bridge-Execution-Token` and the local `MT5_BRIDGE_EXECUTION_TOKEN`. Starting the bridge never submits an order. Execution and management require independent app/bridge permissions and remain disabled and hard-blocked by default. The bridge has no credentials or login endpoint and does not expose raw login, password, server, account identifier, or broker result identifiers.

See `docs/operations/mt5_bridge_setup.md` for the authoritative startup, safety, and shutdown procedure.
