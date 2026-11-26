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
    capital: float = _env_float("QUANTX_CAPITAL", 10000.0)
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
    risk_pct: float = _env_float("QUANTX_RISK_PCT", 0.015)           # 1.0% standard
    a_plus_risk_pct: float = _env_float("QUANTX_APLUS_RISK_PCT", 0.020)  # 1.5% A+
    profit_lock_trigger_pct: float = 0.025  # +2.5% realized daily profit
    profit_lock_risk_mult: float = 0.50     # Halve risk in Profit-Lock mode
    profit_lock_min_score: int = 95         # Only A+ >= 95 setups in Profit-Lock
    max_daily_loss_pct: float = 0.030       # -2.5% daily circuit breaker
    max_open_trades: int = _env_int("QUANTX_MAX_OPEN_TRADES", 2)
    max_daily_trades: int = _env_int("QUANTX_MAX_DAILY_TRADES", 4)

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
