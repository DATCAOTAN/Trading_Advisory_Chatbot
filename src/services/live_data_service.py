"""
Live Data Service — Data Provider Đa Luồng (Multi-API Core)

Tích hợp tự động phân luồng (Auto-Routing):
  - Binance API (Công khai): Cho các mã Crypto (BTCUSDT, ETHUSDT)
  - Oanda API: Cho Forex/Vàng (nếu có API Key trong .env)
  - Yahoo Finance (yfinance): Fallback tự động cho Forex/Vàng nếu không có Oanda.
"""

import os
import json
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from src.config import Config


class LiveDataService:
    """
    Dịch vụ cung cấp dữ liệu thị trường (Data Provider) đa nguồn.
    Cung cấp Giá Thực tế và Nến Quá khứ (Klines) hỗ trợ phân tích SMC/FVG.
    """

    # =========================================================================
    # CONFIG TỪ BIẾN MÔI TRƯỜNG (.env)
    # =========================================================================
    OANDA_API_KEY      = Config.OANDA_API_KEY
    OANDA_ACCOUNT_ID   = Config.OANDA_ACCOUNT_ID
    FOREX_FACTORY_URL  = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    def __init__(self):
        self._price_cache: Dict = {}
        self._calendar_cache: Dict = {}

    def _is_crypto(self, symbol: str) -> bool:
        """Kiểm tra mã tài sản có phải là Crypto hay không."""
        sym_upper = symbol.upper()
        return "USDT" in sym_upper or "BTC" in sym_upper or "ETH" in sym_upper

    # =========================================================================
    # GIÁ LIVE (REAL-TIME)
    # =========================================================================
    def get_live_price(self, symbol: str = "XAUUSD") -> str:
        """
        Lấy giá Live tự động điều hướng API.
        """
        sym = symbol.upper().replace("_", "").replace("/", "")

        try:
            if self._is_crypto(sym):
                return self._get_binance_live_price(sym)
            else:
                if self.OANDA_API_KEY and self.OANDA_ACCOUNT_ID:
                    return self._get_oanda_live_price(sym)
                else:
                    return self._get_yfinance_live_price(sym)
        except Exception as e:
            return f"❌ Lỗi lấy giá Live cho {symbol}: {e}"

    def _get_binance_live_price(self, symbol: str) -> str:
        url = "https://api.binance.com/api/v3/ticker/price"
        params = {"symbol": symbol}
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        price = float(data["price"])
        return f"💰 **{symbol}**: ${price:,.2f} (Cập nhật: {datetime.now().strftime('%H:%M:%S')}) - *Nguồn: Binance*"

    def _get_oanda_live_price(self, symbol: str) -> str:
        # Map XAUUSD sang XAU_USD cho Oanda
        oanda_sym = f"{symbol[:3]}_{symbol[3:]}" if len(symbol) == 6 else symbol
        headers = {"Authorization": f"Bearer {self.OANDA_API_KEY}"}
        url = f"https://api-fxtrade.oanda.com/v3/instruments/{oanda_sym}/candles"
        params = {"count": 1, "granularity": "S5", "price": "M"}
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        price = float(data["candles"][-1]["mid"]["c"])
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime('%H:%M:%S')
        return f"💰 **{symbol}**: ${price:,.2f} (Cập nhật: {vn_time} Giờ VN) - *Nguồn: OANDA*"

    def _get_yfinance_live_price(self, symbol: str) -> str:
        # Map XAUUSD -> GC=F (Vàng tương lai)
        if symbol == "XAUUSD":
            yf_sym = "GC=F"
        else:
            yf_sym = f"{symbol}=X"

        ticker = yf.Ticker(yf_sym)
        # Fast live info
        data = ticker.fast_info
        price = data.last_price
        vn_time = datetime.now(timezone(timedelta(hours=7))).strftime('%H:%M:%S')
        return f"💰 **{symbol}**: ${price:,.2f} (Cập nhật: {vn_time} Giờ VN) - *Nguồn: Yahoo Finance*"

    # =========================================================================
    # NẾN QUÁ KHỨ (HISTORICAL CANDLES) ĐỂ PHÂN TÍCH SMC
    # =========================================================================
    def get_historical_candles(self, symbol: str = "XAUUSD", timeframe: str = "1h", limit: int = 100, target_date: str = None, indicators: List[Dict] = None) -> List[Dict]:
        """
        Lấy dữ liệu nến (OHLCV) cho thuật toán SMC/FVG.
        Trả về: [{"timestamp": str, "open": float, "high": float, "low": float, "close": float, "volume": float}]
        """
        sym = symbol.upper().replace("_", "").replace("/", "")

        padding_limit = limit
        if indicators:
            max_period = max([int(ind.get("period", 0)) for ind in indicators], default=0)
            if max_period > 0:
                padding_limit = max(limit, max_period * 3)

        try:
            if self._is_crypto(sym):
                candles = self._get_binance_candles(sym, timeframe, padding_limit, target_date)
            else:
                if self.OANDA_API_KEY and self.OANDA_ACCOUNT_ID:
                    candles = self._get_oanda_candles(sym, timeframe, padding_limit, target_date)
                else:
                    candles = self._get_yfinance_candles(sym, timeframe, padding_limit, target_date)

            if indicators and candles:
                candles = self._calculate_indicators(candles, indicators)

            if target_date:
                return self._apply_target_date_filter(candles, target_date, indicators)

            return candles[-limit:] if candles else []
        except Exception as e:
            print(f"Lỗi lấy dữ liệu nến {symbol}: {e}")
            return []

    def _apply_target_date_filter(self, candles: List[Dict], target_date: str, indicators: List[Dict] = None) -> List[Dict]:
        if not candles:
            return []

        try:
            fmt = "%Y-%m-%d %H:%M:%S" if len(target_date) > 10 else "%Y-%m-%d"
            tdt_vn = datetime.strptime(target_date, fmt)
            tdt_utc = tdt_vn - timedelta(hours=7)

            valid_candles = []
            for c in candles:
                c_dt_utc = datetime.strptime(c["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
                if c_dt_utc <= tdt_utc:
                    valid_candles.append((c_dt_utc, c))

            if not valid_candles:
                return [{"error": f"Không có dữ liệu nào trước {target_date} (Giờ VN)."}]

            valid_candles.sort(key=lambda x: x[0])
            best_dt_utc, best_candle = valid_candles[-1]

            diff = tdt_utc - best_dt_utc
            if diff.total_seconds() > 3600:
                best_candle["warning"] = f"Không có giao dịch tại chính xác {target_date} Giờ VN (có thể do thị trường nghỉ/cuối tuần). Đây là dữ liệu của cây nến gần nhất trước đó."
            else:
                best_candle["note"] = f"Dữ liệu khớp với thời điểm {target_date} Giờ VN."

            if indicators:
                for ind in indicators:
                    name = str(ind.get("name", "")).lower()
                    period = int(ind.get("period", 14))
                    safe_key = f"{name}_{period}"

                    val = best_candle.get(safe_key)
                    if val is None or pd.isna(val):
                        best_candle[safe_key] = "NaN"
                        if "warning" not in best_candle:
                            best_candle["warning"] = ""
                        best_candle["warning"] += f" | Không đủ dữ liệu lịch sử để tính toán chỉ báo {name.upper()} chu kỳ {period}."

            for k, v in best_candle.items():
                if isinstance(v, float) and pd.isna(v):
                    best_candle[k] = "NaN"

            return [best_candle]

        except Exception as e:
            print(f"Lỗi filter target_date: {e}")
            return candles

    def _calculate_indicators(self, candles: List[Dict], indicators: List[Dict]) -> List[Dict]:
        if not candles or not indicators:
            return candles

        try:
            df = pd.DataFrame(candles)
            if 'close' not in df.columns:
                return candles

            for ind in indicators:
                name = str(ind.get("name", "")).lower()
                period = int(ind.get("period", 14))

                safe_key = f"{name}_{period}"

                if name == "ema":
                    df[safe_key] = df['close'].ewm(span=period, adjust=False).mean()
                elif name == "sma":
                    df[safe_key] = df['close'].rolling(window=period).mean()
                elif name == "rsi":
                    delta = df['close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                    rs = gain / loss
                    df[safe_key] = 100 - (100 / (1 + rs))
                elif name == "macd":
                    exp1 = df['close'].ewm(span=12, adjust=False).mean()
                    exp2 = df['close'].ewm(span=26, adjust=False).mean()
                    df['macd'] = exp1 - exp2
                    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
                    df['macd_hist'] = df['macd'] - df['macd_signal']

            return df.to_dict(orient="records")
        except Exception as e:
            print(f"Lỗi tính chỉ báo: {e}")
            return candles

    def _get_start_dt(self, tdt: datetime, timeframe: str, padding_limit: int) -> datetime:
        days_to_subtract = max(5, int(padding_limit * 1.5))
        if timeframe.endswith("h"):
            days_to_subtract = max(5, int(padding_limit / 24 * 1.5) + 1)
        elif timeframe.endswith("m"):
            days_to_subtract = max(5, int(padding_limit / 1440 * 1.5) + 1)
        return tdt - timedelta(days=days_to_subtract)

    def _get_binance_candles(self, symbol: str, timeframe: str, limit: int, target_date: str = None) -> List[Dict]:
        # Binance map: 1h, 4h, 1d
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": timeframe, "limit": limit}

        if target_date:
            try:
                fmt = "%Y-%m-%d %H:%M:%S" if len(target_date) > 10 else "%Y-%m-%d"
                tdt = datetime.strptime(target_date, fmt)
                # Kéo dữ liệu từ 5 ngày trước đến 1 ngày sau
                start_dt = self._get_start_dt(tdt, timeframe, limit)
                end_dt = tdt + timedelta(days=1)
                params["startTime"] = int(start_dt.timestamp() * 1000)
                params["endTime"] = int(end_dt.timestamp() * 1000)
                params["limit"] = 1000 # Max limit
            except:
                pass

        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        klines = resp.json()

        candles = []
        for k in klines:
            ts = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            candles.append({
                "timestamp": ts,
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5])
            })

        return candles

    def _get_yfinance_candles(self, symbol: str, timeframe: str, limit: int, target_date: str = None) -> List[Dict]:
        if symbol == "XAUUSD":
            yf_sym = "GC=F"
        else:
            yf_sym = f"{symbol}=X"

        # yfinance map
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "1h", "1d": "1d"}
        yf_interval = interval_map.get(timeframe, "1h")

        ticker = yf.Ticker(yf_sym)

        if target_date:
            try:
                fmt = "%Y-%m-%d %H:%M:%S" if len(target_date) > 10 else "%Y-%m-%d"
                tdt = datetime.strptime(target_date, fmt)
                start_dt = self._get_start_dt(tdt, timeframe, limit)
                end_dt = tdt + timedelta(days=2) # Đảm bảo bao phủ
                df = ticker.history(start=start_dt.strftime('%Y-%m-%d'), end=end_dt.strftime('%Y-%m-%d'), interval=yf_interval)
            except:
                df = ticker.history(period="1mo", interval=yf_interval)
        else:
            if yf_interval == "1m":
                period = "5d"
            elif yf_interval in ["5m", "15m", "30m"]:
                period = "1mo"
            elif yf_interval == "1h":
                period = "3mo" if limit > 150 else "1mo"
            elif yf_interval == "1d":
                if limit <= 20:
                    period = "1mo"
                elif limit <= 60:
                    period = "3mo"
                elif limit <= 120:
                    period = "6mo"
                elif limit <= 250:
                    period = "1y"
                elif limit <= 500:
                    period = "2y"
                else:
                    period = "5y"
            else:
                period = "1mo" if limit > 100 else "5d"
            df = ticker.history(period=period, interval=yf_interval)

        if df.empty:
            return []

        if not target_date:
            df = df.tail(limit)

        candles = []
        for index, row in df.iterrows():
            if index.tzinfo is not None:
                utc_dt = index.tz_convert('UTC')
            else:
                utc_dt = index.tz_localize('UTC')

            candles.append({
                "timestamp": utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": float(row['Volume'])
            })

        return candles

    def _get_oanda_candles(self, symbol: str, timeframe: str, limit: int, target_date: str = None) -> List[Dict]:
        oanda_sym = f"{symbol[:3]}_{symbol[3:]}" if len(symbol) == 6 else symbol
        # Oanda map
        tf_map = {"1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30", "1h": "H1", "4h": "H4", "1d": "D"}
        granularity = tf_map.get(timeframe, "H1")

        headers = {"Authorization": f"Bearer {self.OANDA_API_KEY}"}
        url = f"https://api-fxtrade.oanda.com/v3/instruments/{oanda_sym}/candles"
        params = {"granularity": granularity, "price": "M"}

        if target_date:
            try:
                fmt = "%Y-%m-%d %H:%M:%S" if len(target_date) > 10 else "%Y-%m-%d"
                tdt = datetime.strptime(target_date, fmt)
                start_dt = self._get_start_dt(tdt, timeframe, limit)
                end_dt = tdt + timedelta(days=1)
                # Format Oanda RFC3339
                params["from"] = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                params["to"] = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except:
                params["count"] = limit
        else:
            params["count"] = limit

        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        candles = []
        for k in data.get("candles", []):
            if not k["complete"]:
                continue
            candles.append({
                "timestamp": k["time"],
                "open": float(k["mid"]["o"]),
                "high": float(k["mid"]["h"]),
                "low": float(k["mid"]["l"]),
                "close": float(k["mid"]["c"]),
                "volume": float(k["volume"])
            })

        return candles

    # =========================================================================
    # LỊCH KINH TẾ (FOREX FACTORY)
    # =========================================================================
    def get_economic_calendar(self, impact: str = "All") -> str:
        """Lấy lịch kinh tế tuần này từ ForexFactory."""
        try:
            now = datetime.now()
            events = None
            # Dùng cache 1 tiếng để tránh lỗi 429 (Too Many Requests) từ ForexFactory
            if self._calendar_cache and (now - self._calendar_cache.get("time", datetime.min)).total_seconds() < 3600:
                events = self._calendar_cache.get("data")

            if not events:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                }
                # Không dùng proxy vì proxy bị timeout, gọi thẳng kèm timeout ngắn để không lag bot
                resp = requests.get(self.FOREX_FACTORY_URL, headers=headers, timeout=5)
                if resp.status_code != 200:
                    return f"📅 **Lịch Kinh tế**: Tạm thời không thể lấy dữ liệu từ ForexFactory (Mã lỗi: {resp.status_code}). Tường lửa Cloudflare đang chặn kết nối."

                events = resp.json()
                self._calendar_cache["data"] = events
                self._calendar_cache["time"] = now

            if impact and impact != "All":
                target_events = [e for e in events if e.get("impact") == impact]
            else:
                target_events = events

            if not target_events:
                return "📅 **Lịch Kinh tế**: Tuần này không có sự kiện kinh tế nào."

            lines = []
            vn_tz = timezone(timedelta(hours=7))
            for e in target_events:
                date_str = e.get('date', '')
                try:
                    dt = datetime.fromisoformat(date_str)
                    dt_vn = dt.astimezone(vn_tz)
                    date_str = dt_vn.strftime('%d/%m/%Y %H:%M')
                except Exception:
                    pass
                imp = e.get('impact', 'Low')
                lines.append(f"📅 {date_str} | {e.get('country', e.get('currency', 'N/A'))} | [{imp}] {e.get('title', '')}")

            return "**Sự kiện kinh tế tuần này:**\n\n" + "\n".join(lines)

        except Exception as e:
            return f"❌ Lỗi lấy lịch kinh tế: {e}"

    # =========================================================================
    # BÁO CÁO VĨ MÔ
    # =========================================================================
    def get_latest_macro_report(self) -> str:
        return (
            "📊 **Báo cáo Vĩ mô Tự động đang được phát triển.**\n\n"
            "Tính năng sẽ tự động tải và index báo cáo từ SSI Research, WGC vào kho Dynamic PDF."
        )


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
_live_data_service_instance = None

def get_live_service() -> LiveDataService:
    global _live_data_service_instance
    if _live_data_service_instance is None:
        _live_data_service_instance = LiveDataService()
    return _live_data_service_instance

if __name__ == "__main__":
    svc = get_live_service()
    print("Testing Crypto Live Price:")
    print(svc.get_live_price("BTCUSDT"))

    print("\nTesting Crypto Candles:")
    candles = svc.get_historical_candles("BTCUSDT", "1h", 2)
    print(json.dumps(candles, indent=2))

    print("\nTesting Forex/Gold Live Price (Yahoo Finance Fallback):")
    print(svc.get_live_price("XAUUSD"))

    print("\nTesting Forex/Gold Candles:")
    gc_candles = svc.get_historical_candles("XAUUSD", "1h", 2)
    print(json.dumps(gc_candles, indent=2))

    print("\nTesting Economic Calendar:")
    print(svc.get_economic_calendar())
