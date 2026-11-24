# FastAPI Backend + Built-in Mobile Dashboard for INDIAN QUANTX (NSE Cash MIS)
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
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

app = FastAPI(title="INDIAN QUANTX - NSE MIS Algo API", version="1.0.0")


class TickPayload(BaseModel):
    symbol: str
    ltp: float


class KillPayload(BaseModel):
    reason: str = "MANUAL KILL SWITCH"


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>INDIAN QUANTX — Live NSE MIS Terminal</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #090D16; color: #F1F5F9; padding-bottom: 40px;
    }
    .header {
      position: sticky; top: 0; z-index: 20;
      background: rgba(9, 13, 22, 0.95); backdrop-filter: blur(8px);
      border-bottom: 1px solid #1E293B; padding: 12px 16px;
      display: flex; justify-content: space-between; align-items: center; gap: 10px;
    }
    .brand { display: flex; align-items: center; gap: 10px; }
    .logo {
      width: 34px; height: 34px; border-radius: 8px;
      background: rgba(37, 99, 235, 0.2); border: 1px solid rgba(59, 130, 246, 0.45);
      color: #60A5FA; font-weight: 700; font-size: 13px;
      display: flex; align-items: center; justify-content: center;
    }
    .title { font-size: 15px; font-weight: 700; margin: 0; }
    .sub { font-size: 11px; color: #94A3B8; margin: 2px 0 0; }
    .btn {
      border: none; border-radius: 8px; padding: 8px 12px;
      font-size: 12px; font-weight: 600; cursor: pointer;
    }
    .btn-kill { background: rgba(244, 63, 94, 0.18); color: #FDA4AF; border: 1px solid rgba(244, 63, 94, 0.45); }
    .btn-scan { background: #2563EB; color: #FFFFFF; }
    .wrap { max-width: 720px; margin: 0 auto; padding: 14px 16px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 14px; }
    .card {
      background: #111827; border: 1px solid #1E293B; border-radius: 12px;
      padding: 12px 14px; margin-bottom: 10px;
    }
    .kpi-label { font-size: 11px; color: #94A3B8; }
    .kpi-val { font-size: 19px; font-weight: 700; margin-top: 4px; font-family: monospace; }
    .kpi-sub { font-size: 11px; color: #64748B; margin-top: 3px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 12px; overflow-x: auto; }
    .tab {
      background: #111827; color: #94A3B8; border: 1px solid #1E293B;
      border-radius: 8px; padding: 8px 12px; font-size: 12px; font-weight: 600; cursor: pointer;
      white-space: nowrap;
    }
    .tab.active { background: #2563EB; color: #FFF; border-color: #2563EB; }
    .pill {
      display: inline-block; padding: 2px 7px; border-radius: 6px;
      font-size: 10px; font-weight: 700; margin-left: 6px;
    }
    .long { background: rgba(16, 185, 129, 0.18); color: #6EE7B7; }
    .short { background: rgba(244, 63, 94, 0.18); color: #FDA4AF; }
    .green { color: #34D399; }
    .red { color: #FB7185; }
    .muted { color: #94A3B8; font-size: 12px; }
    .halt-box {
      background: rgba(159, 18, 57, 0.25); border: 1px solid rgba(244, 63, 94, 0.5);
      border-radius: 10px; padding: 10px 14px; margin-bottom: 12px; font-size: 12px; color: #FECDD3;
      display: none;
    }
  </style>
</head>
<body>
  <header class="header">
    <div class="brand">
      <div class="logo">QX</div>
      <div>
        <h1 class="title">INDIAN QUANTX · NSE MIS</h1>
        <p class="sub" id="hdrSub">Connecting...</p>
      </div>
    </div>
    <div style="display:flex; gap:8px;">
      <button class="btn btn-scan" onclick="runScan()">Scan</button>
      <button class="btn btn-kill" onclick="triggerKill()">Kill Switch</button>
    </div>
  </header>

  <main class="wrap">
    <div id="haltBox" class="halt-box"></div>

    <div class="kpi-grid">
      <div class="card" style="margin:0;">
        <div class="kpi-label">Capital (5x MIS)</div>
        <div class="kpi-val" id="kCap">-</div>
        <div class="kpi-sub" id="kBp">BP -</div>
      </div>
      <div class="card" style="margin:0;">
        <div class="kpi-label">Realized Net P&amp;L</div>
        <div class="kpi-val" id="kPnl">-</div>
        <div class="kpi-sub" id="kMode">-</div>
      </div>
      <div class="card" style="margin:0;">
        <div class="kpi-label">Open Positions</div>
        <div class="kpi-val" id="kOpen">0 / 3</div>
        <div class="kpi-sub">Max 3 concurrent</div>
      </div>
      <div class="card" style="margin:0;">
        <div class="kpi-label">Daily Trades</div>
        <div class="kpi-val" id="kDaily">0 / 10</div>
        <div class="kpi-sub">Hard Exit: 15:12 IST</div>
      </div>
    </div>

    <div class="tabs">
      <button class="tab active" id="tOpen" onclick="setTab('open')">Active Trades</button>
      <button class="tab" id="tScan" onclick="setTab('scan')">SMC Scanner</button>
      <button class="tab" id="tClosed" onclick="setTab('closed')">Closed Ledger</button>
      <button class="tab" id="tAlerts" onclick="setTab('alerts')">Alerts</button>
    </div>

    <div id="panel"></div>
  </main>

  <script>
    let currentTab = 'open';
    let lastStatus = null;
    let lastScan = [];

    function setTab(t) {
      currentTab = t;
      ['open', 'scan', 'closed', 'alerts'].forEach(x => {
        document.getElementById('t' + x.charAt(0).toUpperCase() + x.slice(1)).classList.toggle('active', x === t);
      });
      render();
    }

    function fmtINR(v) {
      const sign = v >= 0 ? '+₹' : '-₹';
      return sign + Math.abs(v).toLocaleString('en-IN', { maximumFractionDigits: 2 });
    }

    async function loadStatus() {
      try {
        const [sRes, hRes] = await Promise.all([fetch('/status'), fetch('/health')]);
        lastStatus = await sRes.json();
        const h = await hRes.json();
        document.getElementById('hdrSub').textContent =
          h.broker.toUpperCase() + ' Mode · ' + h.ist_time;
        render();
      } catch (e) {
        document.getElementById('hdrSub').textContent = 'Connection error';
      }
    }

    async function runScan() {
      const r = await fetch('/scan/paper', { method: 'POST' });
      const d = await r.json();
      lastScan = d.signals || [];
      setTab('scan');
    }

    async function triggerKill() {
      await fetch('/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Dashboard Kill Switch' })
      });
      await loadStatus();
    }

    function render() {
      if (!lastStatus) return;
      document.getElementById('kCap').textContent = '₹' + Number(lastStatus.capital).toLocaleString('en-IN');
      document.getElementById('kBp').textContent = 'BP ₹' + (lastStatus.buying_power_5x / 100000).toFixed(1) + 'L';

      const pnlEl = document.getElementById('kPnl');
      pnlEl.textContent = fmtINR(lastStatus.realized_net_pnl);
      pnlEl.className = 'kpi-val ' + (lastStatus.realized_net_pnl >= 0 ? 'green' : 'red');

      document.getElementById('kMode').textContent = lastStatus.profit_lock_active ? 'PROFIT-LOCK MODE' : 'STANDARD MODE';
      document.getElementById('kOpen').textContent = lastStatus.open_positions.length + ' / 3';
      document.getElementById('kDaily').textContent = lastStatus.daily_trades_count + ' / ' + lastStatus.max_daily_trades;

      const haltBox = document.getElementById('haltBox');
      if (lastStatus.halted) {
        haltBox.style.display = 'block';
        haltBox.textContent = 'ENGINE HALTED: ' + lastStatus.halt_reason;
      } else {
        haltBox.style.display = 'none';
      }

      const panel = document.getElementById('panel');
      if (currentTab === 'open') {
        const list = lastStatus.open_positions;
        panel.innerHTML = list.length ? list.map(p => `
          <div class="card">
            <div><strong>${p.symbol}</strong><span class="pill ${p.side === 'LONG' ? 'long' : 'short'}">${p.side}</span>
            <span class="muted"> · Score ${p.score} · Stage ${p.stage}/5</span></div>
            <div class="muted" style="margin-top:6px;">
              Entry ₹${p.entry_price} · LTP ₹${p.ltp} · Active SL ₹${p.active_sl} · Qty ${p.rem_qty}/${p.init_qty}
            </div>
          </div>`).join('') : '<div class="card muted">No open NSE MIS positions right now.</div>';
      } else if (currentTab === 'scan') {
        panel.innerHTML = lastScan.length ? lastScan.map(s => `
          <div class="card">
            <div><strong>${s.symbol}</strong><span class="pill ${s.side === 'LONG' ? 'long' : 'short'}">${s.side}</span>
            <span class="muted"> · Score ${s.score} · Entry ₹${s.entry_price} · SL ₹${s.stop_loss}</span></div>
            <div class="muted" style="margin-top:6px;">${s.reason}</div>
          </div>`).join('') : '<div class="card muted">Upar "Scan" button dabakar paper-mode SMC signals dekhein.</div>';
      } else if (currentTab === 'closed') {
        const list = lastStatus.closed_trades;
        panel.innerHTML = list.length ? list.map(c => `
          <div class="card">
            <div><strong>${c.symbol}</strong> (${c.side} · ${c.qty} sh) —
            <strong class="${c.net_pnl >= 0 ? 'green' : 'red'}">${fmtINR(c.net_pnl)} net</strong></div>
            <div class="muted" style="margin-top:6px;">${c.reason} · Costs ₹${c.total_costs}</div>
          </div>`).join('') : '<div class="card muted">Abhi koi closed trade nahi hai.</div>';
      } else {
        const list = lastStatus.alerts;
        panel.innerHTML = list.length ? list.map(a => `
          <div class="card">
            <div><strong>[${a.tag}]</strong> <span class="muted">${a.time}</span></div>
            <div style="font-size:13px; margin-top:4px;">${a.text}</div>
          </div>`).join('') : '<div class="card muted">Abhi koi alert nahi hai.</div>';
      }
    }

    loadStatus();
    setInterval(loadStatus, 3000);
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
        "static_ip": cfg.static_ip_label,
        "ist_time": datetime.now(IST).strftime("%H:%M:%S IST"),
    }


@app.get("/status")
def status() -> dict:
    return manager.status_dict()


@app.post("/scan/paper")
def scan_paper_universe() -> dict:
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
