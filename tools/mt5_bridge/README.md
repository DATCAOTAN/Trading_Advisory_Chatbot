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

There is no execution endpoint, no credentials endpoint, and no login endpoint. The bridge does not expose raw login, password, server, or raw account identifier.
