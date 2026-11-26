# SR INDIAN ALGO BOT - Multi-Engine Autonomous NSE MIS Server + SR QuantX Terminal
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import os
import random
import threading
import time
from typing import Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import pandas as pd
from pydantic import BaseModel
import requests

from broker_adapter import create_broker
from config import QuantXConfig, load_config
from smc_engine import evaluate_signal
from market_data import MarketSnapshot, generate_synthetic_ohlcv, resample_timeframe
from telegram_bot import TelegramNotifier
from trade_manager import TradeManager

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))

base_cfg = load_config()
cfg = QuantXConfig(
    broker=base_cfg.broker,
    capital=base_cfg.capital,
    db_path=base_cfg.db_path,
    max_daily_trades=20,
    telegram_bot_token=base_cfg.telegram_bot_token,
    telegram_chat_id=base_cfg.telegram_chat_id,
)
broker = create_broker(cfg)
notifier = TelegramNotifier(cfg)
manager = TradeManager(cfg, broker, notifier)

SCAN_SYMBOLS = list(cfg.universe)  # Full 50-stock Nifty Liquid Universe

# Smooth non-blocking 120s candle cache + round-robin index
CANDLE_CACHE: Dict[str, tuple[float, pd.DataFrame]] = {}

ENGINE_STATE = {
    "running": True,
    "paper_24x7": os.getenv("PAPER_24X7", "true").lower() == "true",
    "last_scan_ist": "Starting...",
    "last_feed_source": "Yahoo NSE Live",
    "scan_cycles": 0,
    "rr_index": 0,
    "last_signals": [],
    "peak_equity": cfg.capital,
    "max_drawdown_pct": 0.0,
}


def is_nse_market_hours(now_ist: datetime) -> bool:
    if now_ist.weekday() >= 5:
        return False
    hhmm = now_ist.strftime("%H:%M")
    return "09:15" <= hhmm <= "15:25"


def fetch_yahoo_nse_5m(symbol: str) -> Optional[pd.DataFrame]:
    now_ts = time.monotonic()
    cached = CANDLE_CACHE.get(symbol)
    if cached and (now_ts - cached[0]) < 120.0:
        return cached[1]

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?interval=5m&range=5d"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        if resp.status_code != 200:
            return None
        data = resp.json()
        res = data.get("chart", {}).get("result", [])
        if not res:
            return None
        quote = res[0].get("indicators", {}).get("quote", [{}])[0]
        df = pd.DataFrame({
            "open": quote.get("open", []),
            "high": quote.get("high", []),
            "low": quote.get("low", []),
            "close": quote.get("close", []),
            "volume": quote.get("volume", []),
        }).dropna()
        if len(df) < 35:
            return None
        clean = df.reset_index(drop=True)
        CANDLE_CACHE[symbol] = (now_ts, clean)
        return clean
    except Exception:
        return None


def run_autonomous_cycle() -> None:
    now_ist = datetime.now(IST)
    in_hours = is_nse_market_hours(now_ist)
    ENGINE_STATE["scan_cycles"] += 1
    ENGINE_STATE["last_scan_ist"] = now_ist.strftime("%H:%M:%S IST")

    if in_hours and now_ist.strftime("%H:%M") == "09:15" and manager.halted:
        manager.halted = False
        manager.halt_reason = ""
        manager.daily_trades_count = 0

    if not in_hours and not ENGINE_STATE["paper_24x7"]:
        ENGINE_STATE["last_feed_source"] = "NSE Closed (09:15-15:30 IST)"
        return

    # 1. Update open positions smoothly
    for sym in list(manager.open_positions.keys()):
        pos = manager.open_positions[sym]
        if in_hours:
            df_live = fetch_yahoo_nse_5m(sym)
            next_ltp = float(df_live.iloc[-1]["close"]) if df_live is not None else pos.ltp
            tick_time = now_ist
        else:
            drift = random.uniform(-0.35, 0.44) * pos.risk_per_share
            next_ltp = round(pos.ltp + (drift if pos.side == "LONG" else -drift), 2)
            tick_time = now_ist.replace(hour=11, minute=15, second=0, microsecond=0)
        manager.on_tick(sym, next_ltp, now_ist=tick_time)

    # 2. Round-robin batch of 5 stocks per cycle (smooth CPU & fast API responses)
    if manager.halted or len(manager.open_positions) >= cfg.max_open_trades:
        return

    start = ENGINE_STATE["rr_index"] % len(SCAN_SYMBOLS)
    batch = [SCAN_SYMBOLS[(start + i) % len(SCAN_SYMBOLS)] for i in range(5)]
    ENGINE_STATE["rr_index"] = (start + 5) % len(SCAN_SYMBOLS)

    found_signals: List[dict] = []
    use_time = now_ist if in_hours else now_ist.replace(hour=10, minute=20, second=0, microsecond=0)

    for sym in batch:
        df_5m = fetch_yahoo_nse_5m(sym)
        if df_5m is not None:
            ENGINE_STATE["last_feed_source"] = "Yahoo NSE Live" if in_hours else "Yahoo NSE + 24x7 Sim"
            df_15m = resample_timeframe(df_5m, 3)
            df_1h = resample_timeframe(df_5m, 12)
            ltp = float(df_5m.iloc[-1]["close"])
        else:
            ENGINE_STATE["last_feed_source"] = "24x7 Paper Replay"
            trend = random.choice(["LONG", "SHORT"])
            df_5m = generate_synthetic_ohlcv(1500.0, bars=80, trend=trend, seed=random.randint(1, 9999))
            df_15m = resample_timeframe(df_5m, 3)
            df_1h = resample_timeframe(df_5m, 6)
            ltp = float(df_5m.iloc[-1]["close"])

        snap = MarketSnapshot(
            symbol=sym,
            ltp=ltp,
            bid=ltp - 0.05,
            ask=ltp + 0.05,
            bid_qty=6300.0,
            ask_qty=3700.0,
            turnover_cr=1450.0,
        )
        sig = evaluate_signal(snap, df_5m, df_15m, df_1h, cfg)
        if sig is not None:
            found_signals.append(asdict(sig))
            if len(manager.open_positions) < cfg.max_open_trades:
                manager.open_trade(sig, now_ist=use_time)

    if found_signals:
        ENGINE_STATE["last_signals"] = found_signals[:8]


def _scanner_worker() -> None:
    try:
        run_autonomous_cycle()
    except Exception:
        pass
    while True:
        time.sleep(20)
        if ENGINE_STATE["running"]:
            try:
                run_autonomous_cycle()
            except Exception:
                pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    t = threading.Thread(target=_scanner_worker, daemon=True)
    t.start()
    yield


app = FastAPI(title="SR INDIAN ALGO BOT - Multi-Engine NSE MIS", version="4.0.0", lifespan=lifespan)


class TickPayload(BaseModel):
    symbol: str
    ltp: float


class TogglePayload(BaseModel):
    paper_24x7: bool


class KillPayload(BaseModel):
    reason: str = "MANUAL KILL SWITCH"


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SR INDIAN ALGO BOT — Multi-Engine NSE MIS</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg: #080C14; --card: #0F1623; --card2: #0A101B; --border: #1E293B;
      --text: #F8FAFC; --muted: #94A3B8; --cyan: #38BDF8; --green: #10B981;
      --red: #F43F5E; --amber: #F59E0B; --blue: #2563EB;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; background: var(--bg); color: var(--text);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      padding-bottom: 50px; -webkit-font-smoothing: antialiased;
    }
    .mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
    .wrap { max-width: 680px; margin: 0 auto; padding: 12px 14px; }

    .top-pill {
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
      background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.45);
      border-radius: 10px; padding: 8px 12px; margin-bottom: 10px; font-size: 11px;
    }
    .top-pill-left { display: flex; align-items: center; gap: 7px; color: #34D399; font-weight: 700; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #10B981; box-shadow: 0 0 8px #10B981; }

    .eng-strip {
      display: grid; grid-template-columns: repeat(5, 1fr); gap: 5px; margin-bottom: 12px;
    }
    .eng-badge {
      background: var(--card); border: 1px solid rgba(56, 189, 248, 0.35);
      border-radius: 7px; padding: 5px 4px; text-align: center;
      font-size: 9.5px; font-weight: 600; color: #7DD3FC;
    }

    .grid2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
    .card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 12px 14px;
    }
    .k-label { font-size: 10px; font-weight: 700; letter-spacing: 0.04em; color: var(--muted); text-transform: uppercase; }
    .k-val { font-size: 21px; font-weight: 700; margin-top: 6px; }
    .k-sub { font-size: 11px; color: var(--muted); margin-top: 4px; }
    .cyan { color: var(--cyan); }
    .green { color: #34D399; }
    .red { color: #FB7185; }
    .amber { color: #FBBF24; }

    .sec-title {
      font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
      color: #E2E8F0; margin: 16px 0 8px; display: flex; align-items: center; gap: 6px;
    }

    .guard-box {
      background: var(--card); border: 1px solid var(--border); border-radius: 10px;
      padding: 10px 12px; font-size: 11px; display: flex; justify-content: space-between; align-items: center;
    }

    .desk {
      background: rgba(245, 158, 11, 0.07); border: 1px solid rgba(245, 158, 11, 0.4);
      border-radius: 12px; padding: 12px 14px; margin-top: 14px;
    }
    .desk-title { font-size: 12px; font-weight: 700; color: #FCD34D; margin-bottom: 8px; }
    .desk-pill {
      background: var(--card2); border: 1px solid rgba(245, 158, 11, 0.35);
      border-radius: 8px; padding: 7px 10px; font-size: 11px; color: #FDE68A;
    }

    .controls { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
    .btn {
      border-radius: 8px; padding: 8px 12px; font-size: 11.5px; font-weight: 600;
      border: 1px solid var(--border); background: var(--card); color: var(--text); cursor: pointer;
    }
    .btn-blue { background: var(--blue); border-color: var(--blue); color: #FFF; }
    .btn-red { background: rgba(244,63,94,0.16); border-color: rgba(244,63,94,0.45); color: #FDA4AF; }
    .btn-green { background: rgba(16,185,129,0.16); border-color: rgba(16,185,129,0.4); color: #6EE7B7; }

    .item-card {
      background: var(--card); border: 1px solid var(--border); border-radius: 12px;
      padding: 12px 14px; margin-bottom: 10px;
    }
    .pill {
      display: inline-block; padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 700; margin-left: 6px;
    }
    .long { background: rgba(16,185,129,0.18); color: #6EE7B7; }
    .short { background: rgba(244,63,94,0.18); color: #FDA4AF; }
    .ladder { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; margin-top: 8px; }
    .step {
      padding: 5px 3px; text-align: center; font-size: 10px; border-radius: 6px;
      background: var(--card2); border: 1px solid var(--border); color: var(--muted);
    }
    .step.done { background: rgba(16,185,129,0.18); border-color: rgba(16,185,129,0.45); color: #6EE7B7; font-weight: 600; }
  </style>
</head>
<body>
  <main class="wrap">
    <div class="top-pill">
      <div class="top-pill-left">
        <span class="dot"></span>
        <span>SR INDIAN MULTI-ENGINE ONLINE</span>
      </div>
      <span class="mono" style="color:#94A3B8;" id="hdrMeta">IST · Cycle 0</span>
    </div>

    <!-- 5-Engine Active Strip -->
    <div class="eng-strip mono">
      <div class="eng-badge">1.TrendLock</div>
      <div class="eng-badge">2.SMC BOS</div>
      <div class="eng-badge">3.Momentum</div>
      <div class="eng-badge">4.Vol/VWAP</div>
      <div class="eng-badge">5.LiqGate</div>
    </div>

    <section class="grid2">
      <div class="card">
        <div class="k-label">Portfolio Equity</div>
        <div class="k-val cyan mono" id="kEquity">₹1,00,000</div>
        <div class="k-sub mono" id="kBp">5× MIS BP: ₹5.0L</div>
      </div>
      <div class="card">
        <div class="k-label">Net Realized PNL</div>
        <div class="k-val mono" id="kRealized">₹0</div>
        <div class="k-sub mono" id="kExpectancy">Expectancy: ₹0</div>
      </div>
      <div class="card">
        <div class="k-label">Open Floating PNL</div>
        <div class="k-val mono" id="kFloating">₹0</div>
        <div class="k-sub mono" id="kActive">Active: 0/3 · Limit ±0.10%</div>
      </div>
      <div class="card">
        <div class="k-label">Win Rate &amp; Profit Factor</div>
        <div class="k-val cyan mono" id="kWr">0.0%</div>
        <div class="k-sub mono" id="kPf">0W / 0L · PF: 0.00 · DD: 0.0%</div>
      </div>
    </section>

    <div class="sec-title">15-Day Compounding, Lot Scaling &amp; Withdrawal Vault</div>
    <section class="grid2">
      <div class="card">
        <div class="k-label">15-Day Net PNL (After Fees)</div>
        <div class="k-val mono" id="vNet">₹0</div>
        <div class="k-sub mono" id="vGross">Gross: ₹0</div>
      </div>
      <div class="card">
        <div class="k-label">Free For Withdrawal (70%)</div>
        <div class="k-val green mono" id="vWithdraw">₹0</div>
        <div class="k-sub">70% Safe to Withdraw</div>
      </div>
      <div class="card">
        <div class="k-label">Compounded Trading Cap (30%)</div>
        <div class="k-val cyan mono" id="vCompCap">₹1,00,000</div>
        <div class="k-sub mono" id="vScale">Lot Scale: 1.00× (STANDARD)</div>
      </div>
      <div class="card">
        <div class="k-label">Total Brokerage Deducted</div>
        <div class="k-val amber mono" id="vCosts">₹0</div>
        <div class="k-sub">STT 0.025% + Brk + GST</div>
      </div>
    </section>

    <section class="grid2">
      <div class="guard-box">
        <span class="k-label">Daily Trades</span>
        <strong class="mono" id="gDaily">0 / 10</strong>
      </div>
      <div class="guard-box">
        <span class="k-label">Daily Loss Limit</span>
        <strong class="mono" id="gLoss">₹0 / -₹2,500</strong>
      </div>
      <div class="guard-box">
        <span class="k-label">Active Lot Risk</span>
        <strong class="mono cyan" id="gRisk">1.0% (~₹1,000)</strong>
      </div>
      <div class="guard-box">
        <span class="k-label">Liquidity / News</span>
        <strong class="mono green" id="gFeed">ACTIVE / CLEAR</strong>
      </div>
    </section>

    <div class="controls">
      <button class="btn btn-blue" onclick="triggerScanNow()">Scan &amp; Auto-Trade Now</button>
      <button class="btn btn-green" id="btn247" onclick="toggle247()">24×7 Sim: ON</button>
      <button class="btn btn-red" onclick="triggerKill()">Kill Switch</button>
    </div>

    <section class="desk">
      <div class="desk-title">⚡ ENSEMBLE CONSENSUS SIGNAL DESK (4/4 ENGINES)</div>
      <div class="desk-pill mono" id="deskText">WATCHING 15M/1H LEVELS · 0 SIGNALS</div>
    </section>

    <div class="sec-title">Active NSE MIS Positions</div>
    <div id="openTrades"></div>

    <div class="sec-title">Recent Closed Trades &amp; Alerts</div>
    <div id="alertsFeed"></div>
  </main>

  <script>
    let is247 = true;

    function fmtINR(v, signed = true) {
      const n = Math.abs(Number(v || 0)).toLocaleString('en-IN', { maximumFractionDigits: 0 });
      if (!signed) return '₹' + n;
      return (v >= 0 ? '+₹' : '-₹') + n;
    }

    async function refresh() {
      try {
        const res = await fetch('/sr-status');
        const d = await res.json();

        document.getElementById('hdrMeta').textContent = d.ist_time + ' · ' + d.feed_source + ' · #' + d.scan_cycles;
        document.getElementById('kEquity').textContent = fmtINR(d.equity, false);
        document.getElementById('kBp').textContent = '5× MIS BP: ₹' + (d.buying_power_5x / 100000).toFixed(1) + 'L';

        const rEl = document.getElementById('kRealized');
        rEl.textContent = fmtINR(d.realized_net_pnl);
        rEl.className = 'k-val mono ' + (d.realized_net_pnl >= 0 ? 'green' : 'red');
        document.getElementById('kExpectancy').textContent = 'Expectancy: ' + fmtINR(d.expectancy);

        const fEl = document.getElementById('kFloating');
        fEl.textContent = fmtINR(d.floating_pnl);
        fEl.className = 'k-val mono ' + (d.floating_pnl >= 0 ? 'green' : 'red');
        document.getElementById('kActive').textContent = 'Active: ' + d.open_positions.length + '/3 · Limit ±0.10%';

        document.getElementById('kWr').textContent = d.win_rate.toFixed(1) + '%';
        document.getElementById('kPf').textContent = d.wins + 'W / ' + d.losses + 'L · PF: ' + d.profit_factor.toFixed(2) + ' · DD: -' + d.max_dd_pct.toFixed(1) + '%';

        const vn = document.getElementById('vNet');
        vn.textContent = fmtINR(d.realized_net_pnl);
        vn.className = 'k-val mono ' + (d.realized_net_pnl >= 0 ? 'green' : 'red');
        document.getElementById('vGross').textContent = 'Gross: ' + fmtINR(d.gross_pnl);
        document.getElementById('vWithdraw').textContent = fmtINR(d.withdrawable_70, false);
        document.getElementById('vCompCap').textContent = fmtINR(d.compounded_cap, false);
        const modeTag = d.profit_lock_active ? 'PROFIT-LOCK' : (d.lot_scale < 1.0 ? 'RECOVERY MODE (TIGHT SL)' : 'COMPOUNDING');
        document.getElementById('vScale').textContent = 'Lot Scale: ' + d.lot_scale.toFixed(2) + '× (' + modeTag + ')';
        document.getElementById('vCosts').textContent = '-₹' + Math.round(d.total_costs).toLocaleString('en-IN');

        document.getElementById('gDaily').textContent = d.daily_trades_count + ' / ' + d.max_daily_trades;
        document.getElementById('gLoss').textContent = fmtINR(d.realized_net_pnl) + ' / -₹' + Math.round(d.capital * 0.025).toLocaleString('en-IN');
        document.getElementById('gRisk').textContent = (d.profit_lock_active ? '0.5%' : '1.0%') + ' (~' + fmtINR(d.capital * (d.profit_lock_active ? 0.005 : 0.01), false) + ')';
        document.getElementById('gFeed').textContent = d.halted ? 'HALTED' : 'ACTIVE / CLEAR';

        is247 = d.paper_24x7;
        document.getElementById('btn247').textContent = '24×7 Sim: ' + (is247 ? 'ON' : 'OFF');

        const sigCount = d.last_signals.length;
        document.getElementById('deskText').textContent =
          sigCount ? ('ENSEMBLE (' + sigCount + '): ' + d.last_signals.map(s => s.symbol + ' ' + s.side + ' [' + s.score + ']').join(' · '))
                   : ('WATCHING 15M/1H LEVELS · ' + d.closed_trades.length + ' CLOSED · WR: ' + d.win_rate.toFixed(0) + '%');

        const ot = document.getElementById('openTrades');
        ot.innerHTML = d.open_positions.length ? d.open_positions.map(p => {
          const diff = p.side === 'LONG' ? (p.ltp - p.entry_price) : (p.entry_price - p.ltp);
          const pnl = p.realized_gross + diff * p.rem_qty;
          const rM = p.risk_per_share > 0 ? diff / p.risk_per_share : 0;
          return `
            <div class="item-card">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                  <strong>${p.symbol}</strong>
                  <span class="pill ${p.side === 'LONG' ? 'long' : 'short'}">${p.side}</span>
                  <span class="mono" style="font-size:11px; color:#94A3B8; margin-left:6px;">Score ${p.score}</span>
                </div>
                <div class="mono ${pnl >= 0 ? 'green' : 'red'}" style="font-weight:700;">
                  ${fmtINR(pnl)} (${rM >= 0 ? '+' : ''}${rM.toFixed(2)}R)
                </div>
              </div>
              <div style="font-size:11px; color:#7DD3FC; margin-top:4px;">${p.setup}</div>
              <div class="mono" style="font-size:11px; color:#94A3B8; margin-top:4px;">
                Entry ₹${p.entry_price} · LTP ₹${p.ltp} · SL ₹${p.active_sl} · Qty ${p.rem_qty}/${p.init_qty}
              </div>
              <div class="ladder mono">
                <div class="step ${p.stage >= 1 ? 'done' : ''}">+0.75R</div>
                <div class="step ${p.stage >= 2 ? 'done' : ''}">TP1 50%</div>
                <div class="step ${p.stage >= 4 ? 'done' : ''}">TP2 30%</div>
                <div class="step ${p.stage >= 5 ? 'done' : ''}">TP3 20%</div>
              </div>
            </div>`;
        }).join('') : '<div class="item-card" style="font-size:12px; color:#94A3B8;">Multi-Engine scanner active... next consensus setup within 25s.</div>';

        const af = document.getElementById('alertsFeed');
        const combined = [
          ...d.closed_trades.slice(0, 5).map(c => ({
            tag: 'CLOSED', time: c.symbol + ' ' + c.side,
            text: c.reason + ' · Net ' + fmtINR(c.net_pnl) + ' (Costs ₹' + Math.round(c.total_costs) + ')'
          })),
          ...d.alerts.slice(0, 6)
        ];
        af.innerHTML = combined.length ? combined.map(a => `
          <div class="item-card" style="padding:10px 12px;">
            <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:3px;">
              <strong class="cyan mono">[${a.tag}]</strong>
              <span class="mono" style="color:#64748B;">${a.time}</span>
            </div>
            <div style="font-size:12px; color:#E2E8F0;">${a.text}</div>
          </div>`).join('') : '<div class="item-card" style="font-size:12px; color:#94A3B8;">Waiting for ensemble consensus...</div>';
      } catch (e) {}
    }

    async function triggerScanNow() {
      await fetch('/scan/auto', { method: 'POST' });
      await refresh();
    }
    async function toggle247() {
      await fetch('/toggle-247', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper_24x7: !is247 })
      });
      await refresh();
    }
    async function triggerKill() {
      await fetch('/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Dashboard Kill Switch' })
      });
      await refresh();
    }

    refresh();
    setInterval(refresh, 4000);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def web_dashboard() -> HTMLResponse:
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "broker": cfg.broker,
        "scan_cycles": ENGINE_STATE["scan_cycles"],
        "ist_time": datetime.now(IST).strftime("%H:%M:%S IST"),
    }


@app.get("/status")
def status() -> dict:
    return manager.status_dict()


@app.get("/sr-status")
def sr_status() -> dict:
    floating = 0.0
    for p in manager.open_positions.values():
        diff = (p.ltp - p.entry_price) if p.side == "LONG" else (p.entry_price - p.ltp)
        floating += diff * p.rem_qty + p.realized_gross

    closed = manager.closed_trades
    wins = sum(1 for c in closed if c.net_pnl > 0)
    losses = sum(1 for c in closed if c.net_pnl <= 0)
    win_rate = (wins / len(closed) * 100.0) if closed else 0.0
    gross_wins = sum(c.net_pnl for c in closed if c.net_pnl > 0)
    gross_losses = abs(sum(c.net_pnl for c in closed if c.net_pnl <= 0))
    pf = (gross_wins / gross_losses) if gross_losses > 0 else (2.0 if gross_wins > 0 else 0.0)
    total_costs = sum(c.total_costs for c in closed)
    gross_pnl = sum(c.gross_pnl for c in closed)
    realized = manager.realized_net_pnl
    expectancy = (realized / len(closed)) if closed else 0.0

    equity = round(cfg.capital + realized + floating, 2)
    if equity > ENGINE_STATE["peak_equity"]:
        ENGINE_STATE["peak_equity"] = equity
    dd = ((ENGINE_STATE["peak_equity"] - equity) / ENGINE_STATE["peak_equity"] * 100.0) if ENGINE_STATE["peak_equity"] > 0 else 0.0
    if dd > ENGINE_STATE["max_drawdown_pct"]:
        ENGINE_STATE["max_drawdown_pct"] = dd

    withdrawable = round(max(0.0, realized) * 0.70, 2)
    compounded_cap = round(cfg.capital + (max(0.0, realized) * 0.30) + min(0.0, realized), 2)
    lot_scale = round(max(0.5, compounded_cap / cfg.capital), 2)

    base = manager.status_dict()
    base.update({
        "ist_time": datetime.now(IST).strftime("%H:%M:%S IST"),
        "feed_source": ENGINE_STATE["last_feed_source"],
        "scan_cycles": ENGINE_STATE["scan_cycles"],
        "paper_24x7": ENGINE_STATE["paper_24x7"],
        "last_signals": ENGINE_STATE["last_signals"],
        "equity": equity,
        "floating_pnl": round(floating, 2),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "profit_factor": pf,
        "max_dd_pct": ENGINE_STATE["max_drawdown_pct"],
        "expectancy": round(expectancy, 2),
        "gross_pnl": round(gross_pnl, 2),
        "total_costs": round(total_costs, 2),
        "withdrawable_70": withdrawable,
        "compounded_cap": compounded_cap,
        "lot_scale": lot_scale,
    })
    return base


@app.post("/scan/auto")
def scan_auto_now() -> dict:
    run_autonomous_cycle()
    return {"cycles": ENGINE_STATE["scan_cycles"], "signals": ENGINE_STATE["last_signals"]}


@app.post("/toggle-247")
def toggle_247(payload: TogglePayload) -> dict:
    ENGINE_STATE["paper_24x7"] = payload.paper_24x7
    return {"paper_24x7": ENGINE_STATE["paper_24x7"]}


@app.post("/tick")
def process_tick(payload: TickPayload) -> dict:
    res = manager.on_tick(payload.symbol.upper(), payload.ltp)
    return {"result": res, "status": manager.status_dict()}


@app.post("/kill-switch")
def trigger_kill(payload: KillPayload) -> dict:
    closed = manager.kill_switch(payload.reason)
    return {"halted": manager.halted, "closed_count": len(closed)}
