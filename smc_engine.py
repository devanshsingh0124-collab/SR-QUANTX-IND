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
