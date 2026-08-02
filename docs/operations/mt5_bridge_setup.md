# MT5 Bridge Setup

The app uses a host-side MT5 Bridge for real live market data. The bridge runs outside Docker. MetaTrader 5 terminal and the `MetaTrader5` Python package are not installed inside the Docker app.

## Architecture

```text
Docker app
-> MT5BridgeMarketDataProvider
-> http://host.docker.internal:8765
-> Host-side MT5 Bridge
-> MetaTrader5 Python package
-> Local MT5 terminal already logged in by user
```

## Requirements

1. MT5 terminal runs on the Windows host.
2. User manually logs into MT5 terminal.
3. MT5 bridge runs on the Windows host.
4. Docker app reaches bridge through `host.docker.internal`.
5. Do not install MT5 terminal inside Docker.
6. Do not install `MetaTrader5` inside the Docker app.
7. Do not put MT5 login, password, or broker credentials into the app config.

## Start Bridge

Run on the host:

```powershell
.\venv\Scripts\python.exe -m tools.mt5_bridge.server
```

Default health URL:

```text
http://127.0.0.1:8765/health
```

## App Configuration

Docker app:

```text
MARKET_DATA_PROVIDER=mt5_bridge
MT5_BRIDGE_URL=http://host.docker.internal:8765
```

Native local app alternative:

```text
MARKET_DATA_PROVIDER=mt5_bridge
MT5_BRIDGE_URL=http://127.0.0.1:8765
```

## Authentication And Safety Defaults

The bridge loads the repository-local ignored `.env`. Authenticated POST endpoints require the header `X-MT5-Bridge-Execution-Token`, whose value must match `MT5_BRIDGE_EXECUTION_TOKEN` on both caller and host bridge. Do not print or commit the token.

Mutation remains disabled by default through independent app-side and bridge-side enable flags, hard blocks, kill switches, account checks, authority reload, idempotency, and capability validation. Starting the terminal or bridge does not submit or modify an order.

## Live Check

After MT5 terminal and the bridge are running:

```powershell
.\venv\Scripts\python.exe scripts\check_mt5_bridge_live.py
```

The script checks `/health`, `/account`, `/tick?symbol=XAUUSD`, and `/ohlcv?symbol=XAUUSD&timeframe=M15&count=10`. It prints hashed/redacted account details only.

## Troubleshooting

- Terminal closed: open MT5 terminal and log in manually.
- MetaTrader5 package missing: install it in the host Python environment, not Docker.
- Bridge unavailable: start `tools.mt5_bridge.server` on the host.
- Docker cannot reach host: use `MT5_BRIDGE_URL=http://host.docker.internal:8765`.
- Wrong symbol name: set `MT5_SYMBOL_MAP_XAUUSD` to the broker's visible symbol name.
- Empty candles: check the symbol is visible in MT5 Market Watch and the timeframe has data.
- Stale data: confirm terminal connection and market session status.
- Account info unavailable: confirm terminal is logged in; the bridge will not store or submit credentials.

## Bridge Endpoints

Read-only GET endpoints:

- `/health`
- `/account`
- `/symbols`
- `/tick`
- `/ohlcv`
- `/positions`

POST endpoints:

- `/execution/write-skeleton/check`: always blocked diagnostic.
- `/execution/lifecycle-snapshot`: authenticated read-only lifecycle evidence.
- `/execution/reconcile`: authenticated read-only broker-evidence reconciliation.
- `/execution/controlled-submit`: authenticated controlled execution boundary, disabled and hard-blocked by default.
- `/execution/controlled-manage`: authenticated controlled management boundary, disabled and hard-blocked by default.

The bridge has no credentials or login endpoint and cannot switch accounts. It independently validates protected authority before its single isolated production `order_send` call-site can be reached. Public responses redact credentials, account login, protected payload values, and exact broker identifiers.
