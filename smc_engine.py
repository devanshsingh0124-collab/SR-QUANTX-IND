# Multi-Engine Confluence & Ensemble Consensus (5 Engines) for SR INDIAN ALGO BOT
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import numpy as np
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
    score: int             # 0-100 (A+ >= 95)
    reason: str


@dataclass(frozen=True)
class EngineVote:
    name: str
    direction: str         # "LONG" | "SHORT" | "NEUTRAL"
    score: int             # 0-25
    detail: str


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1 / period, adjust=False).mean().replace(0, np.nan)
    rs = gain / loss
    return (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)


def _engine_trend_lock(df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> EngineVote:
    i15 = compute_indicators(df_15m).iloc[-1]
    i1h = compute_indicators(df_1h).iloc[-1]
    up15 = i15["close"] > i15["ema20"] > i15["ema50"]
    dn15 = i15["close"] < i15["ema20"] < i15["ema50"]
    up1h = i1h["close"] > i1h["ema20"]
    dn1h = i1h["close"] < i1h["ema20"]

    if up15 and up1h:
        return EngineVote("TrendLock", "LONG", 25, "15m+1H Bullish")
    if dn15 and dn1h:
        return EngineVote("TrendLock", "SHORT", 25, "15m+1H Bearish")
    if up15:
        return EngineVote("TrendLock", "LONG", 16, "15m Bullish")
    if dn15:
        return EngineVote("TrendLock", "SHORT", 16, "15m Bearish")
    return EngineVote("TrendLock", "NEUTRAL", 0, "Mixed HTF")


def _engine_smc_structure(df_5m: pd.DataFrame, ltp: float) -> EngineVote:
    if len(df_5m) < 20:
        return EngineVote("SMC", "NEUTRAL", 0, "Low bars")
    win = df_5m.iloc[-15:-1]
    swing_hi = float(win["high"].max())
    swing_lo = float(win["low"].min())
    last_bar = df_5m.iloc[-1]
    prev_bar = df_5m.iloc[-2]

    if ltp >= swing_hi * 0.9992:
        return EngineVote("SMC", "LONG", 25, "5m Bullish BOS")
    if float(prev_bar["low"]) < swing_lo and float(last_bar["close"]) > swing_lo:
        return EngineVote("SMC", "LONG", 22, "Bullish Sweep")
    if ltp <= swing_lo * 1.0008:
        return EngineVote("SMC", "SHORT", 25, "5m Bearish BOS")
    if float(prev_bar["high"]) > swing_hi and float(last_bar["close"]) < swing_hi:
        return EngineVote("SMC", "SHORT", 22, "Bearish Sweep")
    return EngineVote("SMC", "NEUTRAL", 8, "In Range")


def _engine_momentum(ind_5m: pd.DataFrame, ltp: float, cfg: QuantXConfig) -> EngineVote:
    last = ind_5m.iloc[-1]
    atr = float(last["atr"])
    adx = float(last["adx"])
    ema20 = float(last["ema20"])
    rsi_val = float(_rsi(ind_5m["close"]).iloc[-1])

    if atr <= 0:
        return EngineVote("Momentum", "NEUTRAL", 0, "Zero ATR")
    ema_dist = abs(ltp - ema20) / atr
    if ema_dist > cfg.ema20_max_atr_dist:
        return EngineVote("Momentum", "NEUTRAL", 0, f"Extended {ema_dist:.1f}x")
    if adx < 18.0:
        return EngineVote("Momentum", "NEUTRAL", 5, f"Low ADX {adx:.0f}")

    pts = 25 if adx >= 24.0 else 20
    if ltp > ema20 and 50.0 <= rsi_val <= 74.0:
        return EngineVote("Momentum", "LONG", pts, f"ADX {adx:.0f} RSI {rsi_val:.0f}")
    if ltp < ema20 and 26.0 <= rsi_val <= 50.0:
        return EngineVote("Momentum", "SHORT", pts, f"ADX {adx:.0f} RSI {rsi_val:.0f}")
    return EngineVote("Momentum", "NEUTRAL", 8, "RSI Neutral")


def _engine_volume_flow(ind_5m: pd.DataFrame, snap: MarketSnapshot, cfg: QuantXConfig) -> EngineVote:
    last = ind_5m.iloc[-1]
    vwap = float(last["vwap"])
    rvol = float(last["rvol"])
    depth = snap.depth_imbalance

    if rvol < 1.10:
        return EngineVote("VolumeFlow", "NEUTRAL", 6, f"Low RVOL {rvol:.1f}x")
    pts = 25 if rvol >= cfg.rvol_min else 19
    if snap.ltp >= vwap and depth >= 0.52:
        return EngineVote("VolumeFlow", "LONG", pts, f"VWAP+ RVOL {rvol:.1f}x")
    if snap.ltp <= vwap and depth <= 0.48:
        return EngineVote("VolumeFlow", "SHORT", pts, f"VWAP- RVOL {rvol:.1f}x")
    return EngineVote("VolumeFlow", "NEUTRAL", 8, "VWAP Conflict")


def evaluate_signal(
    snapshot: MarketSnapshot,
    df_5m: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_1h: pd.DataFrame,
    cfg: QuantXConfig,
) -> Optional[TradeSignal]:
    """Run all 5 engines (Liquidity Gate + 4 Alpha Engines) and return consensus signal."""
    ok, _ = passes_liquidity_gate(snapshot, cfg)
    if not ok or len(df_5m) < 25 or len(df_15m) < 10 or len(df_1h) < 5:
        return None

    ind_5m = compute_indicators(df_5m)
    atr = float(ind_5m.iloc[-1]["atr"])
    adx = float(ind_5m.iloc[-1]["adx"])
    rvol = float(ind_5m.iloc[-1]["rvol"])
    ema20 = float(ind_5m.iloc[-1]["ema20"])
    if atr <= 0:
        return None

    votes: List[EngineVote] = [
        _engine_trend_lock(df_15m, df_1h),
        _engine_smc_structure(df_5m, snapshot.ltp),
        _engine_momentum(ind_5m, snapshot.ltp, cfg),
        _engine_volume_flow(ind_5m, snapshot, cfg),
    ]

    long_votes = [v for v in votes if v.direction == "LONG"]
    short_votes = [v for v in votes if v.direction == "SHORT"]

    if len(long_votes) >= 3 and len(short_votes) == 0:
        side = "LONG"
        aligned = long_votes
    elif len(short_votes) >= 3 and len(long_votes) == 0:
        side = "SHORT"
        aligned = short_votes
    else:
        return None

    consensus_bonus = 18 if len(aligned) == 3 else 12
    total_score = min(100, sum(v.score for v in aligned) + consensus_bonus)
    if total_score < 80:
        return None

    sl_dist = round(atr * (cfg.atr_sl_mult + cfg.atr_wick_cushion), 2)
    if sl_dist <= 0:
        return None
    stop_loss = round(snapshot.ltp - sl_dist, 2) if side == "LONG" else round(snapshot.ltp + sl_dist, 2)
    ema_dist = round(abs(snapshot.ltp - ema20) / atr, 2)
    tags = " | ".join(f"{v.name}:OK" for v in aligned)

    return TradeSignal(
        symbol=snapshot.symbol.upper(),
        side=side,
        entry_price=round(snapshot.ltp, 2),
        stop_loss=stop_loss,
        risk_per_share=sl_dist,
        atr=round(atr, 2),
        adx=round(adx, 2),
        rvol=round(rvol, 2),
        depth_imbalance=round(snapshot.depth_imbalance, 3),
        ema20_atr_dist=ema_dist,
        score=total_score,
        reason=f"[{len(aligned)}/4 Engines] {tags}",
    )
