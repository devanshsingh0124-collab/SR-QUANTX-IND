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
