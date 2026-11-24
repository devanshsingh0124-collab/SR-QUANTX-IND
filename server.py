""FastAPI Backend Server for INDIAN QUANTX (NSE Cash MIS)."""
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
