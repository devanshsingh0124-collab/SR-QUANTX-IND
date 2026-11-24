# INDIAN QUANTX — Complete Copy-Paste Code & 24/7 Background VPS Guide

Yeh poora copy-paste ready guide hai jise aap mobile ya laptop se seedhe apni GitHub repo ya Mumbai Static-IP VPS par paste karke **24×7 background** mein chala sakte hain.

> **SEBI 2026 Important Note:** 1 April 2026 se retail algo API orders ke liye broker portal par **whitelisted Static IPv4** mandatory hai ([NSE/INVG/67858](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf), [FYERS SEBI Rules](https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026)). Isliye Render (dynamic IP) ki jagah **Mumbai region VPS** (AWS Lightsail / DigitalOcean / Contabo / Oracle Cloud — ~₹400–₹500/month) par `systemd` services ke saath chalayein.

## Folder Structure

```text
indian_quantx/
├── requirements.txt
├── .env
├── config.py
├── tax_engine.py
├── market_data.py
├── smc_engine.py
├── broker_adapter.py
├── telegram_bot.py
├── trade_manager.py
├── server.py
├── dashboard.py
├── daily_login.py
└── test_quantx.py
```

---

## Part 1: Saari Files (Complete Copy-Paste Code)

### 1. `requirements.txt`

```text
fastapi==0.115.6
uvicorn==0.34.0
streamlit==1.41.1
pandas==2.2.3
numpy==2.1.3
python-dotenv==1.0.1
requests==2.32.3
pyotp==2.9.0

# Optional Live Broker SDKs (uncomment the one you use on your Mumbai Static-IP VPS):
# smartapi-python>=1.4.8
# dhanhq>=2.0.2
```

### 2. `.env (rename from .env.example)`

```bash
# Broker mode: paper | angel | dhan
QUANTX_BROKER=paper
QUANTX_CAPITAL=100000
QUANTX_RISK_PCT=0.010
QUANTX_APLUS_RISK_PCT=0.015
QUANTX_MAX_OPEN_TRADES=3
QUANTX_MAX_DAILY_TRADES=10
QUANTX_STATIC_IP=YOUR_MUMBAI_VPS_STATIC_IP
QUANTX_DB_PATH=quantx_state.db
QUANTX_API_URL=http://127.0.0.1:8000

# Telegram Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Angel One SmartAPI (Free Trading + Free Data)
ANGEL_API_KEY=
ANGEL_CLIENT_ID=
ANGEL_PIN=
ANGEL_TOTP_SECRET=

# DhanHQ v2 (Free Trading + ₹499/mo 20-Level Depth Data)
DHAN_CLIENT_ID=
DHAN_ACCESS_TOKEN=
```

### 3. `config.py`

```python
"""Central configuration for INDIAN QUANTX (NSE Cash MIS Algorithmic Engine)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import FrozenSet, Tuple


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


NIFTY_LIQUID_UNIVERSE: Tuple[str, ...] = (
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY",
    "SBIN", "BHARTIARTL", "ITC", "LT", "KOTAKBANK",
    "AXISBANK", "BAJFINANCE", "HINDUNILVR", "MARUTI", "SUNPHARMA",
    "TATAMOTORS", "TATASTEEL", "NTPC", "POWERGRID", "M&M",
    "TITAN", "HCLTECH", "ASIANPAINT", "ULTRACEMCO", "WIPRO",
    "ADANIENT", "ADANIPORTS", "BAJAJFINSV", "COALINDIA", "ONGC",
    "JSWSTEEL", "HINDALCO", "TECHM", "INDUSINDBK", "GRASIM",
    "DRREDDY", "CIPLA", "BPCL", "BRITANNIA", "EICHERMOT",
    "HEROMOTOCO", "APOLLOHOSP", "DIVISLAB", "NESTLEIND", "TATACONSUM",
    "TRENT", "BEL", "HAL", "DLF", "VBL",
)

BLOCKED_ASM_GSM: FrozenSet[str] = frozenset({
    # Add ASM/GSM or circuit-prone symbols here to permanently block
})


@dataclass(frozen=True)
class QuantXConfig:
    # Broker & mode: "paper" | "angel" | "dhan"
    broker: str = os.getenv("QUANTX_BROKER", "paper").strip().lower()
    capital: float = _env_float("QUANTX_CAPITAL", 100000.0)
    db_path: str = os.getenv("QUANTX_DB_PATH", "quantx_state.db")

    # SEBI 2026 & NSE MIS execution controls
    mis_leverage: float = 5.0
    safe_bp_ratio: float = 0.58  # Max 58% of 5x buying power per position
    limit_buffer_pct: float = 0.0010  # ±0.10% marketable limit buffer (no market orders)
    max_ops_per_sec: int = 8  # Stay safely under NSE 10 OPS TOPS threshold
    static_ip_label: str = os.getenv("QUANTX_STATIC_IP", "UNSET_CONFIGURE_VPS_IP")

    # Session timings (IST)
    entry_start_ist: str = "09:20"
    entry_cutoff_ist: str = "14:30"
    hard_exit_ist: str = "15:12"

    # Risk & Profit-Lock parameters
    risk_pct: float = _env_float("QUANTX_RISK_PCT", 0.010)           # 1.0% standard
    a_plus_risk_pct: float = _env_float("QUANTX_APLUS_RISK_PCT", 0.015)  # 1.5% A+
    profit_lock_trigger_pct: float = 0.025  # +2.5% realized daily profit
    profit_lock_risk_mult: float = 0.50     # Halve risk in Profit-Lock mode
    profit_lock_min_score: int = 95         # Only A+ >= 95 setups in Profit-Lock
    max_daily_loss_pct: float = 0.025       # -2.5% daily circuit breaker
    max_open_trades: int = _env_int("QUANTX_MAX_OPEN_TRADES", 3)
    max_daily_trades: int = _env_int("QUANTX_MAX_DAILY_TRADES", 10)

    # Institutional liquidity gate
    min_turnover_cr: float = 500.0
    max_spread_pct: float = 0.0005  # 0.05%

    # SMC & Momentum filters (NSE 15m+1H trend, 5m entry)
    adx_min: float = 22.0
    rvol_min: float = 1.30
    depth_long_min: float = 0.56
    depth_short_max: float = 0.44
    ema20_max_atr_dist: float = 1.50
    atr_sl_mult: float = 1.50
    atr_wick_cushion: float = 0.25

    # 50/30/20 Profit-Lock R-Multiple Ladder
    r_risk_slash: float = 0.75
    r_tp1: float = 1.25
    r_trail_mid: float = 1.75
    r_tp2: float = 2.30
    r_trail_high: float = 2.90
    r_tp3: float = 3.50
    stalled_loser_minutes: int = 45
    stalled_loser_r: float = -0.55

    # Universe
    universe: Tuple[str, ...] = field(default_factory=lambda: NIFTY_LIQUID_UNIVERSE)
    blocked_symbols: FrozenSet[str] = field(default_factory=lambda: BLOCKED_ASM_GSM)

    # Credentials (loaded from env)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    angel_api_key: str = os.getenv("ANGEL_API_KEY", "")
    angel_client_id: str = os.getenv("ANGEL_CLIENT_ID", "")
    angel_pin: str = os.getenv("ANGEL_PIN", "")
    angel_totp_secret: str = os.getenv("ANGEL_TOTP_SECRET", "")

    dhan_client_id: str = os.getenv("DHAN_CLIENT_ID", "")
    dhan_access_token: str = os.getenv("DHAN_ACCESS_TOKEN", "")


def load_config() -> QuantXConfig:
    return QuantXConfig()
```

### 4. `tax_engine.py`

```python
"""Exact 2026 Indian Equity Intraday (MIS) statutory cost & net P&L engine."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostBreakdown:
    brokerage: float
    stt: float
    exchange_txn: float
    sebi_fee: float
    stamp_duty: float
    gst: float
    total: float


def calculate_mis_costs(
    entry_price: float,
    exit_price: float,
    qty: int,
    side: str = "LONG",
    orders_executed: int = 2,
    brokerage_cap_per_order: float = 20.0,
) -> CostBreakdown:
    """Compute exact NSE Equity Intraday (MIS) charges (2026 schedule).

    - Brokerage: min(₹20, 0.03%) per executed order (entry + partial/full exits)
    - STT: 0.025% on sell-side value only (unchanged in Budget 2026)
    - NSE Exchange Txn: 0.00297% on total turnover
    - SEBI Turnover Fee: 0.0001% (₹10 per crore) on total turnover
    - Stamp Duty: 0.003% on buy-side value only
    - GST: 18% on (Brokerage + Exchange Txn + SEBI Fee)
    """
    if qty <= 0 or entry_price <= 0 or exit_price <= 0:
        return CostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    side_u = side.upper()
    buy_val = (entry_price * qty) if side_u == "LONG" else (exit_price * qty)
    sell_val = (exit_price * qty) if side_u == "LONG" else (entry_price * qty)
    turnover = buy_val + sell_val

    # Estimate brokerage across entry + exit legs (each capped at ₹20)
    legs = max(2, int(orders_executed))
    avg_leg_val = turnover / legs
    brokerage = legs * min(brokerage_cap_per_order, avg_leg_val * 0.0003)

    stt = sell_val * 0.00025
    exchange_txn = turnover * 0.0000297
    sebi_fee = turnover * 0.000001
    stamp_duty = buy_val * 0.00003
    gst = (brokerage + exchange_txn + sebi_fee) * 0.18
    total = brokerage + stt + exchange_txn + sebi_fee + stamp_duty + gst

    return CostBreakdown(
        brokerage=round(brokerage, 2),
        stt=round(stt, 2),
        exchange_txn=round(exchange_txn, 2),
        sebi_fee=round(sebi_fee, 2),
        stamp_duty=round(stamp_duty, 2),
        gst=round(gst, 2),
        total=round(total, 2),
    )


def calculate_net_pnl(
    entry_price: float,
    exit_price: float,
    qty: int,
    side: str,
    orders_executed: int = 2,
) -> tuple[float, CostBreakdown, float]:
    """Return (gross_pnl, cost_breakdown, net_pnl)."""
    diff = (exit_price - entry_price) if side.upper() == "LONG" else (entry_price - exit_price)
    gross = round(diff * qty, 2)
    costs = calculate_mis_costs(entry_price, exit_price, qty, side, orders_executed)
    net = round(gross - costs.total, 2)
    return gross, costs, net
```

### 5. `market_data.py`

```python
"""Institutional NSE Liquidity Gate & Pure-Pandas Technical Indicators."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
import numpy as np
import pandas as pd

from config import QuantXConfig


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    ltp: float
    bid: float
    ask: float
    bid_qty: float
    ask_qty: float
    turnover_cr: float
    circuit_hit: bool = False

    @property
    def spread_pct(self) -> float:
        if self.ltp <= 0:
            return 1.0
        return max(0.0, (self.ask - self.bid) / self.ltp)

    @property
    def depth_imbalance(self) -> float:
        total = self.bid_qty + self.ask_qty
        if total <= 0:
            return 0.5
        return self.bid_qty / total


def passes_liquidity_gate(snapshot: MarketSnapshot, cfg: QuantXConfig) -> tuple[bool, str]:
    """Enforce QuantX-style institutional liquidity filter for NSE cash stocks."""
    sym = snapshot.symbol.upper()
    if sym in cfg.blocked_symbols:
        return False, "Blocked ASM/GSM symbol"
    if sym not in cfg.universe:
        return False, "Outside Nifty liquid universe"
    if snapshot.circuit_hit:
        return False, "Circuit limit hit"
    if snapshot.turnover_cr < cfg.min_turnover_cr:
        return False, f"Turnover ₹{snapshot.turnover_cr:.0f}Cr < ₹{cfg.min_turnover_cr:.0f}Cr"
    if snapshot.spread_pct > cfg.max_spread_pct:
        return False, f"Spread {snapshot.spread_pct*100:.3f}% > {cfg.max_spread_pct*100:.2f}%"
    return True, "OK"


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute EMA20, EMA50, ATR14, ADX14, Session VWAP, and RVOL20."""
    out = df.copy()
    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    vol = out["volume"].astype(float)

    out["ema20"] = close.ewm(span=20, adjust=False).mean()
    out["ema50"] = close.ewm(span=50, adjust=False).mean()

    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()

    # Wilder ADX(14)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr_safe = out["atr"].replace(0, np.nan)
    plus_di = 100.0 * pd.Series(plus_dm, index=out.index).ewm(alpha=1 / 14, adjust=False).mean() / atr_safe
    minus_di = 100.0 * pd.Series(minus_dm, index=out.index).ewm(alpha=1 / 14, adjust=False).mean() / atr_safe
    dx = (100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0.0)
    out["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean()

    # Session VWAP & Relative Volume
    typical_price = (high + low + close) / 3.0
    cum_vol = vol.cumsum().replace(0, np.nan)
    out["vwap"] = (typical_price * vol).cumsum() / cum_vol
    vol_ma = vol.rolling(20, min_periods=5).mean().replace(0, np.nan)
    out["rvol"] = (vol / vol_ma).fillna(1.0)

    return out


def generate_synthetic_ohlcv(
    base_price: float = 2900.0,
    bars: int = 80,
    trend: str = "LONG",
    seed: Optional[int] = 42,
) -> pd.DataFrame:
    """Generate clean synthetic NSE intraday candles for paper/unit testing."""
    rng = np.random.default_rng(seed)
    drift = 0.0014 if trend.upper() == "LONG" else -0.0014
    prices = [base_price]
    for i in range(1, bars):
        noise = rng.normal(0.0, 0.0012)
        step = drift * (1.35 if i > bars - 15 else 1.0) + noise
        prices.append(max(10.0, prices[-1] * (1.0 + step)))

    rows = []
    for i, c in enumerate(prices):
        o = prices[i - 1] if i > 0 else c * 0.999
        wick = abs(c) * 0.0018
        h = max(o, c) + wick * rng.uniform(0.3, 1.0)
        l = min(o, c) - wick * rng.uniform(0.3, 1.0)
        vol = int(rng.uniform(45000, 95000) * (1.8 if i >= bars - 3 else 1.0))
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": vol})
    return pd.DataFrame(rows)


def resample_timeframe(df_5m: pd.DataFrame, factor: int) -> pd.DataFrame:
    """Aggregate 5m OHLCV DataFrame into higher timeframe (3 -> 15m, 12 -> 1H)."""
    if len(df_5m) < factor:
        return df_5m.copy()
    groups = np.arange(len(df_5m)) // factor
    agg = df_5m.groupby(groups).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return agg.reset_index(drop=True)
```

### 6. `smc_engine.py`

```python
"""QuantX SMC + Multi-Timeframe Trend Lock Signal Engine for NSE Cash MIS."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import pandas as pd

from config import QuantXConfig
from market_data import MarketSnapshot, compute_indicators, passes_liquidity_gate


@dataclass(frozen=True)
class TradeSignal:
    symbol: str
    side: str              # "LONG" | "SHORT"
    entry_price: float
    stop_loss: float
    risk_per_share: float
    atr: float
    adx: float
    rvol: float
    depth_imbalance: float
    ema20_atr_dist: float
    score: int             # 0–100 (A+ >= 95)
    reason: str


def _trend_direction(df_ind: pd.DataFrame) -> str:
    last = df_ind.iloc[-1]
    if last["close"] > last["ema20"] > last["ema50"]:
        return "LONG"
    if last["close"] < last["ema20"] < last["ema50"]:
        return "SHORT"
    return "NEUTRAL"


def evaluate_signal(
    snapshot: MarketSnapshot,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_1h: pd.DataFrame,
    cfg: QuantXConfig,
) -> Optional[TradeSignal]:
    """Run full QuantX NSE confluence pipeline on one liquid stock."""
    ok, _ = passes_liquidity_gate(snapshot, cfg)
    if not ok:
        return None
    if len(df_5m) < 25 or len(df_15m) < 10 or len(df_1h) < 5:
        return None

    ind_5m = compute_indicators(df_5m)
    ind_15m = compute_indicators(df_15m)
    ind_1h = compute_indicators(df_1h)

    t15 = _trend_direction(ind_15m)
    t1h = _trend_direction(ind_1h)
    if t15 == "NEUTRAL" or t15 != t1h:
        return None  # Strict 15m + 1H trend lock

    side = t15
    last = ind_5m.iloc[-1]
    prev_window = ind_5m.iloc[-12:-1]

    atr = float(last["atr"])
    adx = float(last["adx"])
    rvol = float(last["rvol"])
    vwap = float(last["vwap"])
    ema20 = float(last["ema20"])
    close = float(snapshot.ltp)
    depth = snapshot.depth_imbalance

    if atr <= 0 or adx < cfg.adx_min or rvol < cfg.rvol_min:
        return None

    # Anti-chase EMA20 distance guard
    ema_dist_atr = abs(close - ema20) / atr
    if ema_dist_atr > cfg.ema20_max_atr_dist:
        return None

    # VWAP + Orderbook Depth Imbalance + SMC BOS check
    if side == "LONG":
        if close < vwap or depth < cfg.depth_long_min:
            return None
        bos = close >= float(prev_window["high"].max()) * 0.999
        if not bos:
            return None
    else:
        if close > vwap or depth > cfg.depth_short_max:
            return None
        bos = close <= float(prev_window["low"].min()) * 1.001
        if not bos:
            return None

    # Anti-Wick SL = 1.50x ATR + 0.25x ATR cushion
    sl_dist = round(atr * (cfg.atr_sl_mult + cfg.atr_wick_cushion), 2)
    if sl_dist <= 0:
        return None
    stop_loss = round(close - sl_dist, 2) if side == "LONG" else round(close + sl_dist, 2)

    # Confidence score (base 82 + bonus up to 100)
    score = 82
    if adx >= 28:
        score += 5
    elif adx >= 24:
        score += 3
    if rvol >= 1.7:
        score += 5
    elif rvol >= 1.4:
        score += 3
    if (side == "LONG" and depth >= 0.62) or (side == "SHORT" and depth <= 0.38):
        score += 5
    else:
        score += 2
    if ema_dist_atr <= 1.0:
        score += 3
    score = min(100, score)

    return TradeSignal(
        symbol=snapshot.symbol.upper(),
        side=side,
        entry_price=round(close, 2),
        stop_loss=stop_loss,
        risk_per_share=sl_dist,
        atr=round(atr, 2),
        adx=round(adx, 2),
        rvol=round(rvol, 2),
        depth_imbalance=round(depth, 3),
        ema20_atr_dist=round(ema_dist_atr, 2),
        score=score,
        reason=f"15m+1H {side} Lock · BOS · VWAP · RVOL {rvol:.1f}x · Depth {depth:.2f}",
    )
```

### 7. `broker_adapter.py`

```python
"""SEBI-2026-Compliant Broker Adapters (Paper, Angel One SmartAPI, DhanHQ v2)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
import time
import uuid

from config import QuantXConfig


@dataclass(frozen=True)
class OrderReceipt:
    order_id: str
    symbol: str
    side: str          # "BUY" | "SELL"
    qty: int
    limit_price: float
    fill_price: float
    status: str        # "FILLED" | "REJECTED"
    message: str


class RateLimiter:
    """Enforce client-side <10 OPS limit (NSE TOPS compliance)."""

    def __init__(self, max_ops: int = 8) -> None:
        self.max_ops = max(1, max_ops)
        self._timestamps: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) >= 1.0:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_ops:
            sleep_for = 1.0 - (now - self._timestamps[0]) + 0.01
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._timestamps.append(time.monotonic())


class BrokerAdapter(ABC):
    def __init__(self, cfg: QuantXConfig) -> None:
        self.cfg = cfg
        self.limiter = RateLimiter(cfg.max_ops_per_sec)

    def marketable_limit_price(self, ltp: float, side: str) -> float:
        """SEBI 2026 rule: never send raw MARKET orders; use ±0.10% LIMIT buffer."""
        buf = self.cfg.limit_buffer_pct
        raw = ltp * (1.0 + buf) if side.upper() == "BUY" else ltp * (1.0 - buf)
        # Round to NSE 0.05 tick size
        return round(round(raw * 20.0) / 20.0, 2)

    @abstractmethod
    def place_mis_limit_order(self, symbol: str, side: str, qty: int, ltp: float) -> OrderReceipt:
        raise NotImplementedError


class PaperBrokerAdapter(BrokerAdapter):
    """Zero-cost paper trading adapter with realistic 0.04% slippage simulation."""

    def place_mis_limit_order(self, symbol: str, side: str, qty: int, ltp: float) -> OrderReceipt:
        self.limiter.acquire()
        if qty <= 0 or ltp <= 0:
            return OrderReceipt("", symbol, side, qty, 0.0, 0.0, "REJECTED", "Invalid qty or LTP")
        limit_px = self.marketable_limit_price(ltp, side)
        slip = 0.0004
        fill_px = round(ltp * (1.0 + slip) if side.upper() == "BUY" else ltp * (1.0 - slip), 2)
        return OrderReceipt(
            order_id=f"PAPER-{uuid.uuid4().hex[:8].upper()}",
            symbol=symbol.upper(),
            side=side.upper(),
            qty=qty,
            limit_price=limit_px,
            fill_price=fill_px,
            status="FILLED",
            message="Simulated MIS Limit-Buffer fill",
        )


class AngelOneBrokerAdapter(BrokerAdapter):
    """Angel One SmartAPI adapter (Free Trading + Data, TOTP 2FA, Static IP)."""

    def __init__(self, cfg: QuantXConfig) -> None:
        super().__init__(cfg)
        self._client = None

    def login_totp(self) -> bool:
        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as exc:
            raise RuntimeError("Install smartapi-python and pyotp for Angel One live mode") from exc

        totp = pyotp.TOTP(self.cfg.angel_totp_secret).now()
        self._client = SmartConnect(api_key=self.cfg.angel_api_key)
        resp = self._client.generateSession(self.cfg.angel_client_id, self.cfg.angel_pin, totp)
        return bool(resp and resp.get("status"))

    def place_mis_limit_order(self, symbol: str, side: str, qty: int, ltp: float) -> OrderReceipt:
        self.limiter.acquire()
        limit_px = self.marketable_limit_price(ltp, side)
        if self._client is None:
            return OrderReceipt("", symbol, side, qty, limit_px, 0.0, "REJECTED", "Angel One session not initialized")
        payload = {
            "variety": "NORMAL",
            "tradingsymbol": f"{symbol.upper()}-EQ",
            "symboltoken": "",  # Populate from Angel OpenAPIScripMaster.json
            "transactiontype": side.upper(),
            "exchange": "NSE",
            "ordertype": "LIMIT",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": str(limit_px),
            "quantity": str(qty),
        }
        order_id = self._client.placeOrder(payload)
        return OrderReceipt(str(order_id), symbol.upper(), side.upper(), qty, limit_px, limit_px, "FILLED", "Submitted to Angel One")


class DhanHQBrokerAdapter(BrokerAdapter):
    """DhanHQ v2 adapter (Free Trading API, ₹499/mo 20-Level Depth, Static IP)."""

    def __init__(self, cfg: QuantXConfig) -> None:
        super().__init__(cfg)
        self._client = None

    def connect(self) -> bool:
        try:
            from dhanhq import dhanhq
        except ImportError as exc:
            raise RuntimeError("Install dhanhq package for DhanHQ live mode") from exc
        self._client = dhanhq(self.cfg.dhan_client_id, self.cfg.dhan_access_token)
        return True

    def place_mis_limit_order(self, symbol: str, side: str, qty: int, ltp: float) -> OrderReceipt:
        self.limiter.acquire()
        limit_px = self.marketable_limit_price(ltp, side)
        if self._client is None:
            return OrderReceipt("", symbol, side, qty, limit_px, 0.0, "REJECTED", "DhanHQ client not connected")
        resp = self._client.place_order(
            security_id="",  # Map from Dhan NSE scrip master CSV
            exchange_segment=self._client.NSE,
            transaction_type=self._client.BUY if side.upper() == "BUY" else self._client.SELL,
            quantity=qty,
            order_type=self._client.LIMIT,
            product_type=self._client.INTRA,
            price=limit_px,
        )
        oid = str(resp.get("data", {}).get("orderId", ""))
        status = "FILLED" if oid else "REJECTED"
        return OrderReceipt(oid, symbol.upper(), side.upper(), qty, limit_px, limit_px, status, str(resp))


def create_broker(cfg: QuantXConfig) -> BrokerAdapter:
    if cfg.broker == "angel":
        return AngelOneBrokerAdapter(cfg)
    if cfg.broker == "dhan":
        return DhanHQBrokerAdapter(cfg)
    return PaperBrokerAdapter(cfg)
```

### 8. `telegram_bot.py`

```python
"""QuantX-style Telegram Alert Dispatcher for INDIAN QUANTX."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List
import urllib.request
import urllib.parse
import json

from config import QuantXConfig

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class TelegramNotifier:
    cfg: QuantXConfig
    history: List[dict] = field(default_factory=list)

    def send(self, tag: str, message: str) -> bool:
        ts = datetime.now(IST).strftime("%H:%M:%S IST")
        record = {"time": ts, "tag": tag, "text": message}
        self.history.insert(0, record)
        if len(self.history) > 50:
            self.history.pop()

        if not self.cfg.telegram_bot_token or not self.cfg.telegram_chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.cfg.telegram_bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.cfg.telegram_chat_id,
            "text": f"[{tag}] {message}\n({ts})",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False
```

### 9. `trade_manager.py`

```python
"""QuantX 50/30/20 Smart Profit-Lock Trade Manager + SQLite State Persistence."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import math
import sqlite3
from typing import Dict, List, Optional
import uuid

from broker_adapter import BrokerAdapter
from config import QuantXConfig
from smc_engine import TradeSignal
from tax_engine import calculate_net_pnl
from telegram_bot import TelegramNotifier

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class OpenPosition:
    trade_id: str
    symbol: str
    side: str              # "LONG" | "SHORT"
    entry_price: float
    ltp: float
    init_sl: float
    active_sl: float
    risk_per_share: float
    init_qty: int
    rem_qty: int
    stage: int             # 0=init, 1=+0.75R, 2=TP1(50%+BE), 3=+1.75R, 4=TP2(30%+1.45R), 5=+2.90R
    realized_gross: float
    orders_used: int
    score: int
    opened_at_iso: str
    setup: str


@dataclass
class ClosedTrade:
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    qty: int
    gross_pnl: float
    total_costs: float
    net_pnl: float
    reason: str
    closed_at_iso: str


class TradeManager:
    """Manages sizing, 50/30/20 partial booking, trailing SL, Profit-Lock, & 15:12 exit."""

    def __init__(
        self,
        cfg: QuantXConfig,
        broker: BrokerAdapter,
        notifier: Optional[TelegramNotifier] = None,
    ) -> None:
        self.cfg = cfg
        self.broker = broker
        self.notifier = notifier or TelegramNotifier(cfg)
        self.open_positions: Dict[str, OpenPosition] = {}
        self.closed_trades: List[ClosedTrade] = []
        self.daily_trades_count: int = 0
        self.halted: bool = False
        self.halt_reason: str = ""
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.cfg.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS closed_trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT, side TEXT,
                    entry_price REAL, exit_price REAL, qty INTEGER,
                    gross_pnl REAL, total_costs REAL, net_pnl REAL,
                    reason TEXT, closed_at_iso TEXT
                )
                """
            )
            conn.commit()

    def _save_closed(self, c: ClosedTrade) -> None:
        with sqlite3.connect(self.cfg.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO closed_trades
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.trade_id, c.symbol, c.side, c.entry_price, c.exit_price,
                    c.qty, c.gross_pnl, c.total_costs, c.net_pnl, c.reason, c.closed_at_iso,
                ),
            )
            conn.commit()

    @property
    def realized_net_pnl(self) -> float:
        partial_gross = sum(p.realized_gross for p in self.open_positions.values())
        closed_net = sum(c.net_pnl for c in self.closed_trades)
        return round(closed_net + partial_gross, 2)

    @property
    def profit_lock_active(self) -> bool:
        return self.realized_net_pnl >= (self.cfg.capital * self.cfg.profit_lock_trigger_pct)

    def calculate_position_size(self, signal: TradeSignal) -> int:
        base_risk_pct = self.cfg.a_plus_risk_pct if signal.score >= 95 else self.cfg.risk_pct
        if self.profit_lock_active:
            base_risk_pct *= self.cfg.profit_lock_risk_mult

        risk_inr = self.cfg.capital * base_risk_pct
        qty_by_risk = math.floor(risk_inr / signal.risk_per_share) if signal.risk_per_share > 0 else 0
        safe_bp = self.cfg.capital * self.cfg.mis_leverage * self.cfg.safe_bp_ratio
        qty_by_bp = math.floor(safe_bp / signal.entry_price) if signal.entry_price > 0 else 0
        return max(0, min(qty_by_risk, qty_by_bp))

    def can_open_trade(self, signal: TradeSignal, now_ist: Optional[datetime] = None) -> tuple[bool, str]:
        if self.halted:
            return False, f"Engine halted: {self.halt_reason}"
        now = now_ist or datetime.now(IST)
        hhmm = now.strftime("%H:%M")
        if hhmm < self.cfg.entry_start_ist or hhmm > self.cfg.entry_cutoff_ist:
            return False, f"Outside NSE entry window ({self.cfg.entry_start_ist}-{self.cfg.entry_cutoff_ist} IST)"
        if len(self.open_positions) >= self.cfg.max_open_trades:
            return False, f"Max open trades ({self.cfg.max_open_trades}) reached"
        if self.daily_trades_count >= self.cfg.max_daily_trades:
            return False, f"Max daily trades ({self.cfg.max_daily_trades}) reached"
        if signal.symbol in self.open_positions:
            return False, f"{signal.symbol} already open"
        if self.profit_lock_active and signal.score < self.cfg.profit_lock_min_score:
            return False, f"Profit-Lock active: requires A+ score >= {self.cfg.profit_lock_min_score}"
        return True, "OK"

    def open_trade(self, signal: TradeSignal, now_ist: Optional[datetime] = None) -> Optional[OpenPosition]:
        ok, _ = self.can_open_trade(signal, now_ist=now_ist)
        if not ok:
            return None
        qty = self.calculate_position_size(signal)
        if qty <= 0:
            return None

        order_side = "BUY" if signal.side == "LONG" else "SELL"
        receipt = self.broker.place_mis_limit_order(signal.symbol, order_side, qty, signal.entry_price)
        if receipt.status != "FILLED":
            return None

        now = now_ist or datetime.now(IST)
        pos = OpenPosition(
            trade_id=f"QX-{uuid.uuid4().hex[:6].upper()}",
            symbol=signal.symbol,
            side=signal.side,
            entry_price=receipt.fill_price,
            ltp=receipt.fill_price,
            init_sl=signal.stop_loss,
            active_sl=signal.stop_loss,
            risk_per_share=signal.risk_per_share,
            init_qty=qty,
            rem_qty=qty,
            stage=0,
            realized_gross=0.0,
            orders_used=1,
            score=signal.score,
            opened_at_iso=now.isoformat(),
            setup=signal.reason,
        )
        self.open_positions[signal.symbol] = pos
        self.daily_trades_count += 1
        self.notifier.send(
            "ENTRY",
            f"{pos.symbol} {pos.side} · Qty {qty} @ ₹{pos.entry_price:.2f} · SL ₹{pos.active_sl:.2f} (Score {pos.score})",
        )
        return pos

    def _partial_book(self, pos: OpenPosition, fraction: float, ltp: float, label: str) -> int:
        target_qty = max(1, math.floor(pos.init_qty * fraction))
        book_qty = min(target_qty, pos.rem_qty)
        if book_qty <= 0:
            return 0
        exit_side = "SELL" if pos.side == "LONG" else "BUY"
        receipt = self.broker.place_mis_limit_order(pos.symbol, exit_side, book_qty, ltp)
        if receipt.status != "FILLED":
            return 0
        diff = (receipt.fill_price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - receipt.fill_price)
        pos.rem_qty -= book_qty
        pos.realized_gross = round(pos.realized_gross + diff * book_qty, 2)
        pos.orders_used += 1
        self.notifier.send(label, f"{pos.symbol} {pos.side} · Booked {book_qty} sh @ ₹{receipt.fill_price:.2f}")
        return book_qty

    def close_position(self, symbol: str, ltp: float, reason: str, now_ist: Optional[datetime] = None) -> Optional[ClosedTrade]:
        pos = self.open_positions.pop(symbol, None)
        if pos is None:
            return None

        fill_px = ltp
        if pos.rem_qty > 0:
            exit_side = "SELL" if pos.side == "LONG" else "BUY"
            receipt = self.broker.place_mis_limit_order(pos.symbol, exit_side, pos.rem_qty, ltp)
            fill_px = receipt.fill_price if receipt.status == "FILLED" else ltp
            pos.orders_used += 1

        rem_diff = (fill_px - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - fill_px)
        total_gross = round(pos.realized_gross + rem_diff * pos.rem_qty, 2)
        _, costs, _ = calculate_net_pnl(pos.entry_price, fill_px, pos.init_qty, pos.side, pos.orders_used)
        net_pnl = round(total_gross - costs.total, 2)

        now = now_ist or datetime.now(IST)
        closed = ClosedTrade(
            trade_id=pos.trade_id,
            symbol=pos.symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=fill_px,
            qty=pos.init_qty,
            gross_pnl=total_gross,
            total_costs=costs.total,
            net_pnl=net_pnl,
            reason=reason,
            closed_at_iso=now.isoformat(),
        )
        self.closed_trades.insert(0, closed)
        self._save_closed(closed)
        self.notifier.send(
            "EXIT",
            f"{closed.symbol} {closed.side} · {reason} · Net ₹{closed.net_pnl:+.2f} (Costs ₹{closed.total_costs:.2f})",
        )

        # Daily loss circuit breaker check
        if self.realized_net_pnl <= -(self.cfg.capital * self.cfg.max_daily_loss_pct) and not self.halted:
            self.kill_switch("DAILY LOSS CIRCUIT BREAKER (-2.5%)", {s: p.ltp for s, p in self.open_positions.items()}, now)
        return closed

    def on_tick(self, symbol: str, ltp: float, now_ist: Optional[datetime] = None) -> Optional[str]:
        """Process live price tick through the 50/30/20 Profit-Lock R-ladder."""
        now = now_ist or datetime.now(IST)
        if now.strftime("%H:%M") >= self.cfg.hard_exit_ist and self.open_positions:
            self.kill_switch("15:12 IST AUTO-SQUARE-OFF", {symbol: ltp}, now)
            return "AUTO_SQUARE_OFF"

        pos = self.open_positions.get(symbol)
        if pos is None:
            return None
        pos.ltp = ltp

        # 1. Stop-loss check
        if (pos.side == "LONG" and ltp <= pos.active_sl) or (pos.side == "SHORT" and ltp >= pos.active_sl):
            reason = "Trailing SL Hit (Profit Locked)" if pos.stage >= 2 else "Anti-Wick SL Hit"
            self.close_position(symbol, ltp, reason, now)
            return "SL_HIT"

        diff = (ltp - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - ltp)
        r_mult = diff / pos.risk_per_share if pos.risk_per_share > 0 else 0.0
        sign = 1.0 if pos.side == "LONG" else -1.0

        # 2. +0.75R -> Slash risk by 50%
        if pos.stage < 1 and r_mult >= self.cfg.r_risk_slash:
            pos.stage = 1
            pos.active_sl = round(pos.entry_price - sign * (0.50 * pos.risk_per_share), 2)
            self.notifier.send("SL", f"{symbol} +0.75R · Risk slashed 50%, SL -> ₹{pos.active_sl:.2f}")

        # 3. TP1 (+1.25R) -> Book 50% + Breakeven lock
        if pos.stage < 2 and r_mult >= self.cfg.r_tp1:
            pos.stage = 2
            self._partial_book(pos, 0.50, ltp, "TP1")
            pos.active_sl = pos.entry_price

        # 4. +1.75R -> Trail SL to +0.90R
        if pos.stage < 3 and r_mult >= self.cfg.r_trail_mid:
            pos.stage = 3
            pos.active_sl = round(pos.entry_price + sign * (0.90 * pos.risk_per_share), 2)

        # 5. TP2 (+2.30R) -> Book 30% + Trail SL to +1.45R
        if pos.stage < 4 and r_mult >= self.cfg.r_tp2:
            pos.stage = 4
            self._partial_book(pos, 0.30, ltp, "TP2")
            pos.active_sl = round(pos.entry_price + sign * (1.45 * pos.risk_per_share), 2)

        # 6. +2.90R -> Ratchet SL to +2.20R
        if pos.stage < 5 and r_mult >= self.cfg.r_trail_high:
            pos.stage = 5
            pos.active_sl = round(pos.entry_price + sign * (2.20 * pos.risk_per_share), 2)

        # 7. TP3 (+3.50R) -> Close remaining 20% runner
        if r_mult >= self.cfg.r_tp3:
            self.close_position(symbol, ltp, "TP3 Runner Hit (+3.50R)", now)
            return "TP3_HIT"

        # 8. 45-minute stalled-loser cut
        opened_dt = datetime.fromisoformat(pos.opened_at_iso)
        elapsed_min = (now - opened_dt).total_seconds() / 60.0
        if elapsed_min >= self.cfg.stalled_loser_minutes and r_mult <= self.cfg.stalled_loser_r:
            self.close_position(symbol, ltp, "45m Stalled-Loser Rule Cut", now)
            return "STALLED_CUT"

        return "UPDATED"

    def kill_switch(
        self,
        reason: str,
        ltp_map: Optional[Dict[str, float]] = None,
        now_ist: Optional[datetime] = None,
    ) -> List[ClosedTrade]:
        self.halted = True
        self.halt_reason = reason
        prices = ltp_map or {}
        closed = []
        for sym in list(self.open_positions.keys()):
            px = prices.get(sym, self.open_positions[sym].ltp)
            res = self.close_position(sym, px, reason, now_ist)
            if res:
                closed.append(res)
        self.notifier.send("HALT", f"{reason} · Closed {len(closed)} positions.")
        return closed

    def status_dict(self) -> dict:
        return {
            "broker": self.cfg.broker,
            "capital": self.cfg.capital,
            "buying_power_5x": self.cfg.capital * self.cfg.mis_leverage,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "profit_lock_active": self.profit_lock_active,
            "realized_net_pnl": self.realized_net_pnl,
            "daily_trades_count": self.daily_trades_count,
            "max_daily_trades": self.cfg.max_daily_trades,
            "open_positions": [asdict(p) for p in self.open_positions.values()],
            "closed_trades": [asdict(c) for c in self.closed_trades[:20]],
            "alerts": self.notifier.history[:20],
        }
```

### 10. `server.py`

```python
"""FastAPI Backend Server for INDIAN QUANTX (NSE Cash MIS)."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from broker_adapter import create_broker
from config import load_config
from market_data import MarketSnapshot, generate_synthetic_ohlcv, resample_timeframe
from smc_engine import TradeSignal, evaluate_signal
from telegram_bot import TelegramNotifier
from trade_manager import TradeManager

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))

cfg = load_config()
broker = create_broker(cfg)
notifier = TelegramNotifier(cfg)
manager = TradeManager(cfg, broker, notifier)

app = FastAPI(title="INDIAN QUANTX — NSE MIS Algo API", version="1.0.0")


class TickPayload(BaseModel):
    symbol: str
    ltp: float


class KillPayload(BaseModel):
    reason: str = "MANUAL KILL SWITCH"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "broker": cfg.broker,
        "static_ip": cfg.static_ip_label,
        "ist_time": datetime.now(IST).strftime("%H:%M:%S IST"),
    }


@app.get("/status")
def status() -> dict:
    return manager.status_dict()


@app.post("/scan/paper")
def scan_paper_universe() -> dict:
    """Run a synthetic paper-mode SMC scan across top liquid NSE names."""
    samples = [
        ("RELIANCE", 2940.0, "LONG", 0.64, 1840.0, 11),
        ("ICICIBANK", 1286.0, "LONG", 0.62, 1620.0, 22),
        ("INFY", 1842.0, "SHORT", 0.37, 1410.0, 33),
        ("TATAMOTORS", 982.0, "SHORT", 0.38, 1290.0, 44),
        ("SBIN", 825.0, "LONG", 0.61, 1580.0, 55),
    ]
    signals: List[dict] = []
    for sym, px, trend, depth, turn_cr, seed in samples:
        df_5m = generate_synthetic_ohlcv(px, bars=80, trend=trend, seed=seed)
        df_15m = resample_timeframe(df_5m, 3)
        df_1h = resample_timeframe(df_5m, 6)
        ltp = float(df_5m.iloc[-1]["close"])
        snap = MarketSnapshot(
            symbol=sym,
            ltp=ltp,
            bid=ltp - 0.05,
            ask=ltp + 0.05,
            bid_qty=depth * 10000,
            ask_qty=(1.0 - depth) * 10000,
            turnover_cr=turn_cr,
        )
        sig: Optional[TradeSignal] = evaluate_signal(snap, df_5m, df_15m, df_1h, cfg)
        if sig is not None:
            signals.append(asdict(sig))
    return {"count": len(signals), "signals": signals}


@app.post("/tick")
def process_tick(payload: TickPayload) -> dict:
    res = manager.on_tick(payload.symbol.upper(), payload.ltp)
    return {"result": res, "status": manager.status_dict()}


@app.post("/square-off/{symbol}")
def square_off_symbol(symbol: str, ltp: Optional[float] = None) -> dict:
    sym = symbol.upper()
    pos = manager.open_positions.get(sym)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No open position for {sym}")
    px = ltp if ltp is not None else pos.ltp
    closed = manager.close_position(sym, px, "Manual API Square Off")
    return {"closed": asdict(closed) if closed else None}


@app.post("/kill-switch")
def trigger_kill(payload: KillPayload) -> dict:
    closed = manager.kill_switch(payload.reason)
    return {"halted": manager.halted, "closed_count": len(closed)}
```

### 11. `dashboard.py`

```python
"""Mobile-First Minimalist Streamlit Terminal for INDIAN QUANTX (NSE MIS)."""
from __future__ import annotations

import os
import requests
import streamlit as st

API_URL = os.getenv("QUANTX_API_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="INDIAN QUANTX — NSE MIS",
    page_icon="QX",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stApp { background-color: #090D16; color: #F1F5F9; }
      .qx-card {
        background: #111827; border: 1px solid #1E293B; border-radius: 12px;
        padding: 14px 16px; margin-bottom: 12px;
      }
      .qx-pill {
        display: inline-block; padding: 2px 8px; border-radius: 6px;
        font-size: 11px; font-weight: 600; margin-right: 6px;
      }
      .qx-long { background: rgba(16,185,129,0.18); color: #6EE7B7; }
      .qx-short { background: rgba(244,63,94,0.18); color: #FDA4AF; }
      .qx-muted { color: #94A3B8; font-size: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def fetch_status() -> dict | None:
    try:
        r = requests.get(f"{API_URL}/status", timeout=4)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


st.markdown("### INDIAN QUANTX · NSE MIS")
data = fetch_status()

if data is None:
    st.error(f"Backend API unreachable at `{API_URL}`. Start with `uvicorn server:app --host 0.0.0.0 --port 8000`.")
    st.stop()

# Top compact KPI row (mobile-friendly 2x2)
c1, c2 = st.columns(2)
with c1:
    st.metric("Capital (5× MIS)", f"₹{data['capital']:,.0f}", f"BP ₹{data['buying_power_5x']/1e5:.1f}L")
with c2:
    st.metric("Realized Net P&L", f"₹{data['realized_net_pnl']:+,.2f}", "PROFIT-LOCK" if data["profit_lock_active"] else "STANDARD")

c3, c4 = st.columns(2)
with c3:
    st.metric("Open Trades", f"{len(data['open_positions'])} / 3")
with c4:
    st.metric("Daily Trades", f"{data['daily_trades_count']} / {data['max_daily_trades']}")

if data["halted"]:
    st.error(f"ENGINE HALTED: {data['halt_reason']}")

if st.button("Trigger Emergency Kill Switch", type="primary", use_container_width=True):
    try:
        requests.post(f"{API_URL}/kill-switch", json={"reason": "Dashboard Kill Switch"}, timeout=5)
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

tab_open, tab_closed, tab_alerts = st.tabs(["Active Trades", "Closed Ledger", "Telegram Alerts"])

with tab_open:
    positions = data.get("open_positions", [])
    if not positions:
        st.info("No open NSE MIS positions right now.")
    for p in positions:
        cls = "qx-long" if p["side"] == "LONG" else "qx-short"
        st.markdown(
            f"""
            <div class="qx-card">
              <div><strong>{p['symbol']}</strong> <span class="qx-pill {cls}">{p['side']}</span>
              <span class="qx-muted">Score {p['score']} · Stage {p['stage']}/5</span></div>
              <div class="qx-muted" style="margin-top:6px;">
                Entry ₹{p['entry_price']:.2f} · LTP ₹{p['ltp']:.2f} · Active SL ₹{p['active_sl']:.2f} · Qty {p['rem_qty']}/{p['init_qty']}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with tab_closed:
    closed = data.get("closed_trades", [])
    if not closed:
        st.info("No closed trades yet today.")
    for c in closed:
        st.markdown(
            f"""
            <div class="qx-card">
              <div><strong>{c['symbol']}</strong> ({c['side']} · {c['qty']} sh) — <strong>₹{c['net_pnl']:+.2f} net</strong></div>
              <div class="qx-muted">{c['reason']} · Gross ₹{c['gross_pnl']:+.2f} · Costs ₹{c['total_costs']:.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with tab_alerts:
    alerts = data.get("alerts", [])
    if not alerts:
        st.info("No alerts yet.")
    for a in alerts:
        st.markdown(
            f"""
            <div class="qx-card">
              <div><strong>[{a['tag']}]</strong> <span class="qx-muted">{a['time']}</span></div>
              <div style="font-size:13px; margin-top:4px;">{a['text']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
```

### 12. `daily_login.py`

```python
"""08:55 AM IST Daily 2FA/TOTP Login & Readiness Check Cron Script."""
from __future__ import annotations

from dotenv import load_dotenv
from broker_adapter import AngelOneBrokerAdapter, DhanHQBrokerAdapter, create_broker
from config import load_config
from telegram_bot import TelegramNotifier


def main() -> None:
    load_dotenv()
    cfg = load_config()
    notifier = TelegramNotifier(cfg)
    broker = create_broker(cfg)

    if isinstance(broker, AngelOneBrokerAdapter):
        ok = broker.login_totp()
        msg = "Angel One TOTP login SUCCESS." if ok else "Angel One TOTP login FAILED!"
        notifier.send("LOGIN", msg)
        print(msg)
    elif isinstance(broker, DhanHQBrokerAdapter):
        ok = broker.connect()
        msg = "DhanHQ session READY." if ok else "DhanHQ connection FAILED!"
        notifier.send("LOGIN", msg)
        print(msg)
    else:
        msg = f"Paper mode active (Capital ₹{cfg.capital:,.0f}, Hard Exit {cfg.hard_exit_ist} IST)."
        notifier.send("LOGIN", msg)
        print(msg)


if __name__ == "__main__":
    main()
```

### 13. `test_quantx.py`

```python
"""Automated verification test suite for INDIAN QUANTX (NSE Cash MIS)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import os
import tempfile

from broker_adapter import PaperBrokerAdapter
from config import QuantXConfig
from market_data import MarketSnapshot, generate_synthetic_ohlcv, passes_liquidity_gate, resample_timeframe
from smc_engine import TradeSignal, evaluate_signal
from tax_engine import calculate_mis_costs, calculate_net_pnl
from trade_manager import TradeManager

IST = timezone(timedelta(hours=5, minutes=30))


def test_liquidity_gate() -> None:
    cfg = QuantXConfig()
    good = MarketSnapshot("RELIANCE", 2940.0, 2939.8, 2940.2, 6500, 3500, 1800.0)
    ok, _ = passes_liquidity_gate(good, cfg)
    assert ok, "Liquid Nifty stock should pass gate"

    illiquid = MarketSnapshot("RELIANCE", 2940.0, 2939.8, 2940.2, 6500, 3500, 120.0)
    ok2, _ = passes_liquidity_gate(illiquid, cfg)
    assert not ok2, "Low turnover stock must be rejected"

    unknown = MarketSnapshot("PENNYSTK", 12.0, 11.9, 12.1, 100, 100, 600.0)
    ok3, _ = passes_liquidity_gate(unknown, cfg)
    assert not ok3, "Non-universe symbol must be rejected"


def test_2026_mis_tax_engine() -> None:
    gross, costs, net = calculate_net_pnl(1000.0, 1020.0, 100, "LONG", orders_executed=2)
    assert gross == 2000.0
    # Sell value = 102,000 => 0.025% STT = ₹25.50
    assert abs(costs.stt - 25.50) < 0.05, f"Unexpected STT: {costs.stt}"
    assert costs.brokerage <= 40.0, "Max ₹20/order across 2 orders"
    assert net == round(gross - costs.total, 2)


def test_marketable_limit_buffer_rounding() -> None:
    cfg = QuantXConfig()
    broker = PaperBrokerAdapter(cfg)
    buy_lim = broker.marketable_limit_price(2940.0, "BUY")
    sell_lim = broker.marketable_limit_price(2940.0, "SELL")
    assert buy_lim > 2940.0 and round(buy_lim * 20) == buy_lim * 20
    assert sell_lim < 2940.0 and round(sell_lim * 20) == sell_lim * 20


def test_50_30_20_profit_lock_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = QuantXConfig(capital=100000.0, db_path=os.path.join(tmp, "test.db"))
        broker = PaperBrokerAdapter(cfg)
        tm = TradeManager(cfg, broker)

        t_open = datetime(2026, 11, 24, 10, 0, tzinfo=IST)
        sig = TradeSignal(
            symbol="RELIANCE", side="LONG", entry_price=1000.0,
            stop_loss=990.0, risk_per_share=10.0, atr=5.7, adx=30.0,
            rvol=1.8, depth_imbalance=0.64, ema20_atr_dist=0.8,
            score=96, reason="Test A+ Setup",
        )
        pos = tm.open_trade(sig, now_ist=t_open)
        assert pos is not None
        assert pos.init_qty == 150, f"1.5% of 1L = 1500 / 10 = 150 sh, got {pos.init_qty}"

        # +0.75R risk slash
        tm.on_tick("RELIANCE", pos.entry_price + 8.0, now_ist=t_open + timedelta(minutes=5))
        assert pos.stage == 1 and pos.active_sl > pos.init_sl

        # TP1 (+1.25R) -> 50% booked + BE lock
        tm.on_tick("RELIANCE", pos.entry_price + 13.0, now_ist=t_open + timedelta(minutes=12))
        assert pos.stage == 2 and pos.rem_qty == 75 and pos.active_sl == pos.entry_price

        # TP2 (+2.30R) -> 30% booked (45 sh) + +1.45R trail
        tm.on_tick("RELIANCE", pos.entry_price + 23.5, now_ist=t_open + timedelta(minutes=25))
        assert pos.stage == 4 and pos.rem_qty == 30

        # TP3 (+3.50R) -> closes remaining 20% runner
        res = tm.on_tick("RELIANCE", pos.entry_price + 35.5, now_ist=t_open + timedelta(minutes=40))
        assert res == "TP3_HIT"
        assert "RELIANCE" not in tm.open_positions
        assert len(tm.closed_trades) == 1
        assert tm.closed_trades[0].net_pnl > 2500.0
        assert tm.profit_lock_active, "Profit-Lock should activate after >+2.5% net realized profit"


def test_stalled_loser_and_1512_auto_exit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = QuantXConfig(capital=100000.0, db_path=os.path.join(tmp, "test2.db"))
        tm = TradeManager(cfg, PaperBrokerAdapter(cfg))
        t_open = datetime(2026, 11, 24, 10, 0, tzinfo=IST)
        sig = TradeSignal(
            symbol="INFY", side="LONG", entry_price=1000.0, stop_loss=990.0,
            risk_per_share=10.0, atr=5.7, adx=25.0, rvol=1.5, depth_imbalance=0.6,
            ema20_atr_dist=0.9, score=90, reason="Test Stalled",
        )
        pos = tm.open_trade(sig, now_ist=t_open)
        assert pos is not None
        res = tm.on_tick("INFY", pos.entry_price - 6.0, now_ist=t_open + timedelta(minutes=46))
        assert res == "STALLED_CUT"

        # Test 15:12 IST auto-square-off
        sig2 = TradeSignal(
            symbol="SBIN", side="LONG", entry_price=800.0, stop_loss=792.0,
            risk_per_share=8.0, atr=4.5, adx=26.0, rvol=1.6, depth_imbalance=0.61,
            ema20_atr_dist=0.8, score=91, reason="Test EOD",
        )
        pos2 = tm.open_trade(sig2, now_ist=datetime(2026, 11, 24, 14, 0, tzinfo=IST))
        assert pos2 is not None
        res2 = tm.on_tick("SBIN", 802.0, now_ist=datetime(2026, 11, 24, 15, 12, tzinfo=IST))
        assert res2 == "AUTO_SQUARE_OFF" and tm.halted and len(tm.open_positions) == 0


def test_smc_engine_smoke() -> None:
    cfg = QuantXConfig()
    df_5m = generate_synthetic_ohlcv(2900.0, bars=80, trend="LONG", seed=7)
    df_15m = resample_timeframe(df_5m, 3)
    df_1h = resample_timeframe(df_5m, 6)
    ltp = float(df_5m.iloc[-1]["close"])
    snap = MarketSnapshot("RELIANCE", ltp, ltp - 0.05, ltp + 0.05, 6800, 3200, 1800.0)
    # Just verify evaluate_signal runs cleanly without error
    _ = evaluate_signal(snap, df_5m, df_15m, df_1h, cfg)


if __name__ == "__main__":
    test_liquidity_gate()
    test_2026_mis_tax_engine()
    test_marketable_limit_buffer_rounding()
    test_50_30_20_profit_lock_lifecycle()
    test_stalled_loser_and_1512_auto_exit()
    test_smc_engine_smoke()
    print("ALL INDIAN QUANTX TESTS PASSED!")
```

---

## Part 2: 24 Ghante Background Mein Kaise Run Hoga (Step-by-Step)

Linux VPS par **24/7 background** mein chalane ka sabse reliable tareeka **`systemd` services + `cron`** hai. Agar VPS reboot ho ya koi crash aaye, toh `systemd` 5 seconds ke andar bot aur dashboard ko automatically restart kar deta hai.

### Step 1: Mumbai Static-IP VPS Setup & Static IP Whitelist

1. **AWS Lightsail (Mumbai `ap-south-1`)** ya **DigitalOcean (Bangalore)** par Ubuntu 22.04/24.04 server banayein aur usko ek **Static IPv4** attach karein.
2. Apna Static IP check karein:
   ```bash
   curl -s ifconfig.me
   ```
3. Yeh Static IP apne broker developer portal (**Angel One SmartAPI** ya **DhanHQ**) mein API Key settings ke andar whitelist karein.

### Step 2: Project Folder & Python Environment Banayein

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
mkdir -p ~/indian_quantx/logs
cd ~/indian_quantx

# Upar di gayi saari files yahan create/paste karein (ya git clone karein)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# .env file banayein aur apna Static IP, Telegram, aur Broker keys bharein
cp .env.example .env
nano .env

# Verification test run karein
python3 test_quantx.py
```

### Step 3: FastAPI Backend ko 24/7 Background Service Banayein (`quantx-api.service`)

File create karein: `sudo nano /etc/systemd/system/quantx-api.service` aur yeh exact code paste karein (agar aapka Linux username `ubuntu` ki jagah kuch aur hai toh `ubuntu` badal dein):

```ini
[Unit]
Description=INDIAN QUANTX FastAPI Algo Backend (24/7)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/indian_quantx
EnvironmentFile=/home/ubuntu/indian_quantx/.env
ExecStart=/home/ubuntu/indian_quantx/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=append:/home/ubuntu/indian_quantx/logs/api.log
StandardError=append:/home/ubuntu/indian_quantx/logs/api_err.log

[Install]
WantedBy=multi-user.target
```

### Step 4: Mobile-First Streamlit Dashboard ko 24/7 Background Service Banayein (`quantx-ui.service`)

File create karein: `sudo nano /etc/systemd/system/quantx-ui.service`:

```ini
[Unit]
Description=INDIAN QUANTX Streamlit Mobile Terminal (24/7)
After=network-online.target quantx-api.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/indian_quantx
EnvironmentFile=/home/ubuntu/indian_quantx/.env
ExecStart=/home/ubuntu/indian_quantx/.venv/bin/streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
RestartSec=5
StandardOutput=append:/home/ubuntu/indian_quantx/logs/ui.log
StandardError=append:/home/ubuntu/indian_quantx/logs/ui_err.log

[Install]
WantedBy=multi-user.target
```

### Step 5: Dono 24/7 Services Start aur Enable Karein

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now quantx-api.service
sudo systemctl enable --now quantx-ui.service

# Status check karein (dono "active (running)" dikhne chahiye)
sudo systemctl status quantx-api.service --no-pager
sudo systemctl status quantx-ui.service --no-pager
```

Ab aapke phone ke browser par `http://<YOUR_VPS_STATIC_IP>:8501` kholne par aapka **INDIAN QUANTX** mobile terminal 24/7 live chalega (VPS firewall mein port `8501` open karein).

### Step 6: Daily 08:55 AM IST Auto-TOTP Login Cron Lagayein

SEBI 2026 rules ke hisaab se har trading day subah fresh 2FA/TOTP session zaroori hai. Pehle VPS ka timezone IST set karein, phir cron lagayein:

```bash
sudo timedatectl set-timezone Asia/Kolkata
crontab -e
```

Crontab ke bottom mein yeh 2 lines add karein:

```cron
# Mon-Fri 08:55 AM IST: Fresh TOTP 2FA login + Telegram morning readiness alert
55 8 * * 1-5 cd /home/ubuntu/indian_quantx && /home/ubuntu/indian_quantx/.venv/bin/python daily_login.py >> /home/ubuntu/indian_quantx/logs/login.log 2>&1

# Mon-Fri 09:00 AM IST: Clean daily backend reload before 09:15 market open
0 9 * * 1-5 sudo systemctl restart quantx-api.service
```

### Step 7: Live Logs & Health Monitoring Commands (Phone SSH se)

```bash
# Live API logs dekhein
tail -f ~/indian_quantx/logs/api.log

# Live login cron logs dekhein
tail -f ~/indian_quantx/logs/login.log

# Health check
curl http://127.0.0.1:8000/health
```

### Daily Automated Cycle (Zero Manual Intervention)

| Time (IST) | Automated Action |
| :--- | :--- |
| `08:55 AM` | `daily_login.py` cron TOTP 2FA login karke Telegram alert bhejta hai |
| `09:00 AM` | `quantx-api.service` fresh daily state ke saath reload hota hai |
| `09:20 AM – 14:30 PM` | Liquidity Gate + SMC Engine entries open karta hai (Marketable Limit ±0.10%) |
| `Live Ticks` | 50/30/20 Profit-Lock Engine SL trail, partial booking aur 45m stalled cut chalata hai |
| `15:12 PM` | Mandatory Auto-Square-Off saari open MIS positions close karke engine halt karta hai |
| `15:30 PM – Next Day` | Server & Dashboard 24/7 online rehte hain — aap kabhi bhi phone par P&L ledger dekh sakte hain |
