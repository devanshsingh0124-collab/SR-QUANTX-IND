# FastAPI Backend + Institutional Mobile-First Terminal for INDIAN QUANTX (NSE Cash MIS)
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
from tax_engine import calculate_mis_costs
from telegram_bot import TelegramNotifier
from trade_manager import TradeManager

load_dotenv()

IST = timezone(timedelta(hours=5, minutes=30))

cfg = load_config()
broker = create_broker(cfg)
notifier = TelegramNotifier(cfg)
manager = TradeManager(cfg, broker, notifier)

app = FastAPI(title="INDIAN QUANTX - NSE MIS Algo Terminal", version="2.0.0")


class TickPayload(BaseModel):
    symbol: str
    ltp: float


class ExecuteDemoPayload(BaseModel):
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
    risk_per_share: float
    atr: float
    adx: float
    rvol: float
    depth_imbalance: float
    ema20_atr_dist: float
    score: int
    reason: str


class KillPayload(BaseModel):
    reason: str = "MANUAL KILL SWITCH"


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>INDIAN QUANTX — Institutional NSE MIS Terminal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg: #070B12;
      --surface: #0F1623;
      --surface-2: #0A0F1A;
      --border: #1E293B;
      --text: #F1F5F9;
      --muted: #94A3B8;
      --dim: #64748B;
      --blue: #2563EB;
      --blue-soft: rgba(37, 99, 235, 0.16);
      --green: #10B981;
      --green-soft: rgba(16, 185, 129, 0.16);
      --red: #F43F5E;
      --red-soft: rgba(244, 63, 94, 0.16);
      --amber: #F59E0B;
      --amber-soft: rgba(245, 158, 11, 0.16);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding-bottom: 56px;
      -webkit-font-smoothing: antialiased;
    }
    .mono { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }

    /* Sticky Top Bar */
    .topbar {
      position: sticky; top: 0; z-index: 30;
      background: rgba(7, 11, 18, 0.94);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--border);
    }
    .topbar-inner {
      max-width: 960px; margin: 0 auto; padding: 12px 16px;
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
    }
    .brand { display: flex; align-items: center; gap: 10px; }
    .logo {
      width: 36px; height: 36px; border-radius: 9px;
      background: var(--blue-soft); border: 1px solid rgba(59, 130, 246, 0.45);
      color: #60A5FA; font-weight: 700; font-size: 13px;
      display: flex; align-items: center; justify-content: center;
    }
    .title-row { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
    .title { font-size: 15px; font-weight: 700; margin: 0; letter-spacing: -0.01em; }
    .tag {
      font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 5px;
      border: 1px solid rgba(59, 130, 246, 0.35); background: var(--blue-soft); color: #93C5FD;
    }
    .tag-amber {
      border-color: rgba(245, 158, 11, 0.35); background: var(--amber-soft); color: #FCD34D;
    }
    .sub {
      font-size: 11px; color: var(--muted); margin: 3px 0 0;
      display: flex; align-items: center; gap: 6px;
    }
    .dot {
      width: 7px; height: 7px; border-radius: 50%; background: var(--green);
      display: inline-block; box-shadow: 0 0 8px var(--green);
    }
    .actions { display: flex; align-items: center; gap: 8px; }
    .btn {
      border: 1px solid transparent; border-radius: 8px; padding: 8px 13px;
      font-size: 12px; font-weight: 600; cursor: pointer; transition: 0.15s ease;
      font-family: inherit;
    }
    .btn:disabled { opacity: 0.45; cursor: not-allowed; }
    .btn-primary { background: var(--blue); color: #FFF; }
    .btn-primary:hover:not(:disabled) { background: #1D4ED8; }
    .btn-kill { background: var(--red-soft); color: #FDA4AF; border-color: rgba(244, 63, 94, 0.45); }
    .btn-kill:hover:not(:disabled) { background: rgba(244, 63, 94, 0.28); }
    .btn-ghost { background: #151E2E; color: #CBD5E1; border-color: var(--border); }
    .btn-ghost:hover:not(:disabled) { background: #1E293B; }
    .btn-green { background: var(--green-soft); color: #6EE7B7; border-color: rgba(16, 185, 129, 0.35); }
    .btn-red { background: var(--red-soft); color: #FDA4AF; border-color: rgba(244, 63, 94, 0.35); }

    /* Compliance Strip */
    .compliance-bar {
      border-top: 1px solid rgba(30, 41, 59, 0.7);
      background: #0A101B;
    }
    .compliance-inner {
      max-width: 960px; margin: 0 auto; padding: 6px 16px;
      display: flex; align-items: center; gap: 12px; overflow-x: auto;
      font-size: 11px; color: var(--muted); white-space: nowrap;
    }
    .compliance-inner::-webkit-scrollbar { display: none; }
    .ok-item { color: #6EE7B7; }

    /* Main Container */
    .wrap { max-width: 960px; margin: 0 auto; padding: 16px; }

    /* KPI Grid */
    .kpi-grid {
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px;
      margin-bottom: 14px;
    }
    @media (min-width: 768px) {
      .kpi-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    }
    .kpi-card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 12px; padding: 13px 14px;
    }
    .kpi-top { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
    .kpi-label { font-size: 11px; color: var(--muted); font-weight: 500; }
    .kpi-badge { font-size: 10px; color: #93C5FD; }
    .kpi-val { font-size: 20px; font-weight: 700; margin-top: 6px; letter-spacing: -0.02em; }
    .kpi-sub { font-size: 11px; color: var(--dim); margin-top: 4px; }

    /* Tabs */
    .tabs {
      display: flex; gap: 8px; border-bottom: 1px solid var(--border);
      padding-bottom: 10px; margin-bottom: 14px; overflow-x: auto;
    }
    .tabs::-webkit-scrollbar { display: none; }
    .tab {
      background: var(--surface); color: var(--muted); border: 1px solid var(--border);
      border-radius: 8px; padding: 8px 13px; font-size: 12.5px; font-weight: 600;
      cursor: pointer; white-space: nowrap; display: flex; align-items: center; gap: 6px;
    }
    .tab.active { background: var(--blue); color: #FFF; border-color: var(--blue); }
    .tab-count {
      font-size: 10px; padding: 1px 6px; border-radius: 5px;
      background: rgba(255,255,255,0.12);
    }

    /* Cards */
    .card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 12px; padding: 14px 16px; margin-bottom: 12px;
    }
    .card-head {
      display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap;
    }
    .sym { font-size: 16px; font-weight: 700; color: #FFF; }
    .pill {
      display: inline-block; padding: 2px 7px; border-radius: 5px;
      font-size: 10px; font-weight: 700; margin-left: 6px; border: 1px solid transparent;
    }
    .long { background: var(--green-soft); color: #6EE7B7; border-color: rgba(16,185,129,0.35); }
    .short { background: var(--red-soft); color: #FDA4AF; border-color: rgba(244,63,94,0.35); }
    .score-pill {
      background: #172033; color: #CBD5E1; border-color: var(--border);
    }
    .score-aplus {
      background: var(--amber-soft); color: #FCD34D; border-color: rgba(245,158,11,0.4);
    }
    .metrics-row {
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px;
      background: var(--surface-2); border: 1px solid rgba(30,41,59,0.8);
      border-radius: 9px; padding: 10px 12px; margin: 12px 0;
    }
    @media (min-width: 640px) {
      .metrics-row { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    }
    .m-label { font-size: 10px; color: var(--dim); display: block; }
    .m-val { font-size: 13px; font-weight: 600; color: var(--text); }

    /* 50/30/20 Ladder */
    .ladder-title {
      display: flex; justify-content: space-between; font-size: 10px; color: var(--muted);
      margin-bottom: 6px;
    }
    .ladder {
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px;
      margin-bottom: 12px;
    }
    .step {
      padding: 6px 4px; border-radius: 6px; text-align: center; font-size: 10px;
      background: #0A0F1A; border: 1px solid var(--border); color: var(--dim);
    }
    .step.done {
      background: var(--green-soft); border-color: rgba(16,185,129,0.45);
      color: #6EE7B7; font-weight: 600;
    }
    .card-foot {
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
      flex-wrap: wrap; padding-top: 10px; border-top: 1px solid rgba(30,41,59,0.7);
    }
    .green { color: #34D399; }
    .red { color: #FB7185; }
    .muted { color: var(--muted); font-size: 12px; }

    /* Banners & Modal */
    .halt-box {
      background: rgba(159, 18, 57, 0.25); border: 1px solid rgba(244, 63, 94, 0.5);
      border-radius: 10px; padding: 12px 14px; margin-bottom: 14px;
      display: none; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;
    }
    .modal-bg {
      position: fixed; inset: 0; background: rgba(0,0,0,0.72); backdrop-filter: blur(4px);
      display: none; align-items: center; justify-content: center; padding: 16px; z-index: 50;
    }
    .modal {
      width: 100%; max-width: 380px; background: var(--surface);
      border: 1px solid rgba(244,63,94,0.45); border-radius: 14px; padding: 18px;
    }
    .toast {
      position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%);
      background: #111827; border: 1px solid #334155; color: #F8FAFC;
      padding: 10px 16px; border-radius: 10px; font-size: 12px; font-weight: 500;
      display: none; z-index: 60; box-shadow: 0 12px 30px rgba(0,0,0,0.5);
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <div class="logo mono">QX</div>
        <div>
          <div class="title-row">
            <h1 class="title">INDIAN QUANTX</h1>
            <span class="tag mono">NSE MIS</span>
            <span class="tag tag-amber mono" id="modeBadge">PAPER</span>
          </div>
          <p class="sub">
            <span class="dot" id="liveDot"></span>
            <span id="hdrSub" class="mono">Syncing terminal...</span>
          </p>
        </div>
      </div>
      <div class="actions">
        <button class="btn btn-primary" id="btnScan" onclick="runScan()">Scan Universe</button>
        <button class="btn btn-kill" onclick="openKillModal()">Kill Switch</button>
      </div>
    </div>
    <div class="compliance-bar">
      <div class="compliance-inner mono">
        <span class="ok-item">✓ SEBI 2026 Static-IP Ready</span>
        <span>|</span>
        <span>Order: Limit Buffer (±0.10%)</span>
        <span>|</span>
        <span>Rate Cap: &lt;8 OPS</span>
        <span>|</span>
        <span>50/30/20 Profit-Lock</span>
        <span>|</span>
        <span style="color:#FCD34D;">Hard Exit: 15:12 IST</span>
      </div>
    </div>
  </header>

  <main class="wrap">
    <div id="haltBox" class="halt-box">
      <div>
        <strong style="font-size:12px; color:#FDA4AF;" id="haltTitle">ENGINE HALTED</strong>
        <div style="font-size:12px; color:#FECDD3; margin-top:2px;" id="haltReason"></div>
      </div>
    </div>

    <!-- KPI Grid -->
    <section class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">Capital (5× MIS)</span>
          <span class="kpi-badge mono" id="kBp">BP ₹5.0L</span>
        </div>
        <div class="kpi-val mono" id="kCap">-</div>
        <div class="kpi-sub">1.0% Risk · 1.5% A+</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">Net P&amp;L (Post-Tax)</span>
          <span class="kpi-badge mono" id="kPct">0.00%</span>
        </div>
        <div class="kpi-val mono" id="kPnl">-</div>
        <div class="kpi-sub mono" id="kCosts">Costs: ₹0</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">Risk Engine</span>
          <span class="kpi-badge mono">Max -2.5%</span>
        </div>
        <div class="kpi-val" id="kMode" style="font-size:16px; margin-top:8px;">STANDARD</div>
        <div class="kpi-sub" id="kModeSub">Profit-Lock at +2.5%</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-top">
          <span class="kpi-label">Slots &amp; Cap</span>
          <span class="kpi-badge mono" id="kDaily">0 / 10 day</span>
        </div>
        <div class="kpi-val mono" id="kOpen">0 / 3</div>
        <div class="kpi-sub">45m Stalled-Loser Cut</div>
      </div>
    </section>

    <!-- Tabs -->
    <nav class="tabs">
      <button class="tab active" id="tOpen" onclick="setTab('open')">
        Active Trades <span class="tab-count mono" id="bOpen">0</span>
      </button>
      <button class="tab" id="tScan" onclick="setTab('scan')">
        SMC Scanner <span class="tab-count mono" id="bScan">0</span>
      </button>
      <button class="tab" id="tClosed" onclick="setTab('closed')">
        Tax &amp; Ledger <span class="tab-count mono" id="bClosed">0</span>
      </button>
      <button class="tab" id="tAlerts" onclick="setTab('alerts')">
        Telegram Log <span class="tab-count mono" id="bAlerts">0</span>
      </button>
    </nav>

    <div id="panel"></div>
  </main>

  <!-- Kill Switch Modal -->
  <div id="killModal" class="modal-bg">
    <div class="modal">
      <h3 style="margin:0; font-size:16px;">Trigger Emergency Kill Switch?</h3>
      <p class="muted" style="margin:8px 0 16px; line-height:1.5;">
        Yeh saari open NSE MIS positions ko immediate Limit Buffer (±0.10%) order se close karega aur engine ko halt kar dega.
      </p>
      <div style="display:flex; justify-content:flex-end; gap:8px;">
        <button class="btn btn-ghost" onclick="closeKillModal()">Cancel</button>
        <button class="btn btn-kill" onclick="confirmKill()">Square Off &amp; Halt</button>
      </div>
    </div>
  </div>

  <div id="toast" class="toast"></div>

  <script>
    let currentTab = 'open';
    let lastStatus = null;
    let lastScan = [];
    let toastTimer = null;

    function showToast(msg) {
      const el = document.getElementById('toast');
      el.textContent = msg;
      el.style.display = 'block';
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => { el.style.display = 'none'; }, 2800);
    }

    function setTab(t) {
      currentTab = t;
      ['open', 'scan', 'closed', 'alerts'].forEach(x => {
        document.getElementById('t' + x.charAt(0).toUpperCase() + x.slice(1)).classList.toggle('active', x === t);
      });
      render();
    }

    function fmtINR(v, signed = true) {
      const num = Math.abs(Number(v || 0)).toLocaleString('en-IN', { maximumFractionDigits: 2 });
      if (!signed) return '₹' + num;
      return (v >= 0 ? '+₹' : '-₹') + num;
    }

    async function loadStatus() {
      try {
        const [sRes, hRes] = await Promise.all([fetch('/status'), fetch('/health')]);
        lastStatus = await sRes.json();
        const h = await hRes.json();
        document.getElementById('modeBadge').textContent = h.broker.toUpperCase();
        document.getElementById('hdrSub').textContent = h.ist_time + ' · IP: ' + h.static_ip;
        render();
      } catch (e) {
        document.getElementById('hdrSub').textContent = 'Reconnecting...';
      }
    }

    async function runScan() {
      const btn = document.getElementById('btnScan');
      btn.disabled = true;
      btn.textContent = 'Scanning...';
      try {
        const r = await fetch('/scan/paper', { method: 'POST' });
        const d = await r.json();
        lastScan = d.signals || [];
        document.getElementById('bScan').textContent = lastScan.length;
        setTab('scan');
        showToast(lastScan.length + ' liquid SMC setups found');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Scan Universe';
      }
    }

    async function executeSignal(idx) {
      const sig = lastScan[idx];
      if (!sig) return;
      const r = await fetch('/execute-paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(sig)
      });
      const d = await r.json();
      if (!r.ok) {
        showToast(d.detail || 'Cannot open trade');
        return;
      }
      showToast(sig.symbol + ' ' + sig.side + ' (' + d.position.init_qty + ' sh) opened!');
      currentTab = 'open';
      await loadStatus();
      setTab('open');
    }

    async function nudgeLtp(symbol, ltp, riskPerShare, side, rDelta) {
      const move = riskPerShare * rDelta;
      const nextLtp = side === 'LONG' ? +(ltp + move).toFixed(2) : +(ltp - move).toFixed(2);
      const r = await fetch('/tick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, ltp: nextLtp })
      });
      const d = await r.json();
      if (d.result && d.result !== 'UPDATED') {
        showToast(symbol + ': ' + d.result);
      }
      await loadStatus();
    }

    async function squareOff(symbol, ltp) {
      await fetch('/square-off/' + encodeURIComponent(symbol) + '?ltp=' + encodeURIComponent(ltp), { method: 'POST' });
      showToast(symbol + ' squared off via Limit Buffer');
      await loadStatus();
    }

    function openKillModal() { document.getElementById('killModal').style.display = 'flex'; }
    function closeKillModal() { document.getElementById('killModal').style.display = 'none'; }

    async function confirmKill() {
      closeKillModal();
      await fetch('/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Dashboard Kill Switch' })
      });
      showToast('Kill Switch executed!');
      await loadStatus();
    }

    function render() {
      if (!lastStatus) return;

      const cap = Number(lastStatus.capital || 0);
      let openUnrealized = 0;
      let totalClosedCosts = 0;
      lastStatus.open_positions.forEach(p => {
        const diff = p.side === 'LONG' ? (p.ltp - p.entry_price) : (p.entry_price - p.ltp);
        openUnrealized += diff * p.rem_qty;
      });
      lastStatus.closed_trades.forEach(c => { totalClosedCosts += Number(c.total_costs || 0); });

      const combinedPnl = Number(lastStatus.realized_net_pnl || 0) + openUnrealized;
      const pct = cap > 0 ? (combinedPnl / cap) * 100 : 0;

      document.getElementById('kCap').textContent = fmtINR(cap, false);
      document.getElementById('kBp').textContent = 'BP ₹' + (lastStatus.buying_power_5x / 100000).toFixed(1) + 'L';

      const pnlEl = document.getElementById('kPnl');
      pnlEl.textContent = fmtINR(combinedPnl, true);
      pnlEl.className = 'kpi-val mono ' + (combinedPnl >= 0 ? 'green' : 'red');

      const pctEl = document.getElementById('kPct');
      pctEl.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
      pctEl.style.color = pct >= 0 ? '#34D399' : '#FB7185';
      document.getElementById('kCosts').textContent = 'Realized Costs: ₹' + Math.round(totalClosedCosts);

      const modeEl = document.getElementById('kMode');
      if (lastStatus.profit_lock_active) {
        modeEl.textContent = 'PROFIT-LOCK';
        modeEl.style.color = '#FCD34D';
        document.getElementById('kModeSub').textContent = '50% risk · A+ (≥95) only';
      } else {
        modeEl.textContent = 'STANDARD';
        modeEl.style.color = '#93C5FD';
        document.getElementById('kModeSub').textContent = 'Profit-Lock at +2.5%';
      }

      document.getElementById('kOpen').textContent = lastStatus.open_positions.length + ' / 3';
      document.getElementById('kDaily').textContent = lastStatus.daily_trades_count + ' / ' + lastStatus.max_daily_trades + ' day';

      document.getElementById('bOpen').textContent = lastStatus.open_positions.length;
      document.getElementById('bScan').textContent = lastScan.length;
      document.getElementById('bClosed').textContent = lastStatus.closed_trades.length;
      document.getElementById('bAlerts').textContent = lastStatus.alerts.length;

      const haltBox = document.getElementById('haltBox');
      if (lastStatus.halted) {
        haltBox.style.display = 'flex';
        document.getElementById('haltReason').textContent = lastStatus.halt_reason;
      } else {
        haltBox.style.display = 'none';
      }

      const panel = document.getElementById('panel');
      if (currentTab === 'open') {
        const list = lastStatus.open_positions;
        if (!list.length) {
          panel.innerHTML = '<div class="card"><strong style="font-size:14px;">No Open NSE MIS Positions</strong><p class="muted" style="margin:6px 0 0;">Upar <b>Scan Universe</b> dabakar liquid Nifty stocks scan karein aur kisi setup par <b>Execute MIS</b> test karein.</p></div>';
          return;
        }
        panel.innerHTML = list.map(p => {
          const diff = p.side === 'LONG' ? (p.ltp - p.entry_price) : (p.entry_price - p.ltp);
          const rMult = p.risk_per_share > 0 ? diff / p.risk_per_share : 0;
          const totalPnl = p.realized_gross + diff * p.rem_qty;
          const scoreCls = p.score >= 95 ? 'score-aplus' : 'score-pill';
          return `
            <article class="card">
              <div class="card-head">
                <div>
                  <span class="sym">${p.symbol}</span>
                  <span class="pill ${p.side === 'LONG' ? 'long' : 'short'}">${p.side}</span>
                  <span class="pill mono ${scoreCls}">Score ${p.score}</span>
                  <div class="muted" style="margin-top:4px;">${p.setup}</div>
                </div>
                <div style="text-align:right;">
                  <div class="mono ${totalPnl >= 0 ? 'green' : 'red'}" style="font-size:16px; font-weight:700;">${fmtINR(totalPnl, true)}</div>
                  <div class="mono ${rMult >= 0 ? 'green' : 'red'}" style="font-size:12px;">${rMult >= 0 ? '+' : ''}${rMult.toFixed(2)}R</div>
                </div>
              </div>

              <div class="metrics-row mono">
                <div><span class="m-label">Entry</span><span class="m-val">₹${p.entry_price.toFixed(2)}</span></div>
                <div><span class="m-label">Live LTP</span><span class="m-val" style="color:#93C5FD;">₹${p.ltp.toFixed(2)}</span></div>
                <div><span class="m-label">Active SL</span><span class="m-val" style="color:#FCD34D;">₹${p.active_sl.toFixed(2)}</span></div>
                <div><span class="m-label">Qty (Rem/Init)</span><span class="m-val">${p.rem_qty} / ${p.init_qty}</span></div>
              </div>

              <div class="ladder-title mono">
                <span>50 / 30 / 20 PROFIT-LOCK LADDER</span>
                <span>Stage ${p.stage} / 5</span>
              </div>
              <div class="ladder mono">
                <div class="step ${p.stage >= 1 ? 'done' : ''}">${p.stage >= 1 ? '✓ ' : ''}+0.75R Slash</div>
                <div class="step ${p.stage >= 2 ? 'done' : ''}">${p.stage >= 2 ? '✓ ' : ''}TP1 50%+BE</div>
                <div class="step ${p.stage >= 4 ? 'done' : ''}">${p.stage >= 4 ? '✓ ' : ''}TP2 30% Trail</div>
                <div class="step ${p.stage >= 5 ? 'done' : ''}">${p.stage >= 5 ? '✓ ' : ''}TP3 20% Run</div>
              </div>

              <div class="card-foot">
                <div style="display:flex; gap:6px;">
                  <button class="btn btn-green mono" onclick="nudgeLtp('${p.symbol}', ${p.ltp}, ${p.risk_per_share}, '${p.side}', 0.5)">+0.5R</button>
                  <button class="btn btn-red mono" onclick="nudgeLtp('${p.symbol}', ${p.ltp}, ${p.risk_per_share}, '${p.side}', -0.5)">-0.5R</button>
                </div>
                <button class="btn btn-ghost" onclick="squareOff('${p.symbol}', ${p.ltp})">Square Off (Limit)</button>
              </div>
            </article>`;
        }).join('');
      } else if (currentTab === 'scan') {
        if (!lastScan.length) {
          panel.innerHTML = '<div class="card muted">Upar <b>Scan Universe</b> button dabakar Nifty 50 liquid SMC setups scan karein.</div>';
          return;
        }
        panel.innerHTML = lastScan.map((s, idx) => {
          const isOpen = lastStatus.open_positions.some(p => p.symbol === s.symbol);
          const scoreCls = s.score >= 95 ? 'score-aplus' : 'score-pill';
          return `
            <article class="card">
              <div class="card-head" style="align-items:center;">
                <div>
                  <div>
                    <span class="sym">${s.symbol}</span>
                    <span class="pill ${s.side === 'LONG' ? 'long' : 'short'}">${s.side}</span>
                    <span class="pill mono ${scoreCls}">Score ${s.score}</span>
                  </div>
                  <div class="muted" style="margin-top:5px;">${s.reason}</div>
                  <div class="mono muted" style="font-size:11px; margin-top:4px;">
                    Entry ₹${s.entry_price} · Anti-Wick SL ₹${s.stop_loss} · ADX ${s.adx} · Depth ${s.depth_imbalance}
                  </div>
                </div>
                <button class="btn ${isOpen ? 'btn-ghost' : 'btn-primary'}" ${isOpen ? 'disabled' : ''} onclick="executeSignal(${idx})">
                  ${isOpen ? 'In Position' : 'Execute MIS'}
                </button>
              </div>
            </article>`;
        }).join('');
      } else if (currentTab === 'closed') {
        const list = lastStatus.closed_trades;
        if (!list.length) {
          panel.innerHTML = '<div class="card muted">Abhi koi closed trade nahi hai. Trade close hone par yahan 2026 STT + Brokerage + GST breakdown dikhega.</div>';
          return;
        }
        panel.innerHTML = list.map(c => `
          <article class="card">
            <div class="card-head">
              <div>
                <span class="sym" style="font-size:15px;">${c.symbol}</span>
                <span class="pill ${c.side === 'LONG' ? 'long' : 'short'}">${c.side} · ${c.qty} sh</span>
                <div class="muted" style="margin-top:4px;">${c.reason} · ₹${c.entry_price} → ₹${c.exit_price}</div>
              </div>
              <div style="text-align:right;" class="mono">
                <div class="${c.net_pnl >= 0 ? 'green' : 'red'}" style="font-size:15px; font-weight:700;">${fmtINR(c.net_pnl, true)} net</div>
                <div class="muted" style="font-size:11px;">Gross ${fmtINR(c.gross_pnl, true)} · Costs ₹${c.total_costs}</div>
              </div>
            </div>
          </article>`).join('');
      } else {
        const list = lastStatus.alerts;
        if (!list.length) {
          panel.innerHTML = '<div class="card muted">Abhi koi Telegram alert log nahi hai.</div>';
          return;
        }
        panel.innerHTML = list.map(a => `
          <article class="card">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
              <span class="tag mono">${a.tag}</span>
              <span class="muted mono" style="font-size:11px;">${a.time}</span>
            </div>
            <div style="font-size:13px; color:#E2E8F0; line-height:1.5;">${a.text}</div>
          </article>`).join('');
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


@app.post("/execute-paper")
def execute_paper_signal(payload: ExecuteDemoPayload) -> dict:
    if cfg.broker != "paper":
        raise HTTPException(status_code=403, detail="Manual demo execution only enabled in paper mode")
    sig = TradeSignal(**payload.model_dump())
    # Use a valid 10:15 IST intraday timestamp in paper mode so user can test 24/7
    demo_time = datetime.now(IST).replace(hour=10, minute=15, second=0, microsecond=0)
    ok, msg = manager.can_open_trade(sig, now_ist=demo_time)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    pos = manager.open_trade(sig, now_ist=demo_time)
    if pos is None:
        raise HTTPException(status_code=400, detail="Order rejected by paper broker")
    return {"position": asdict(pos)}


@app.post("/tick")
def process_tick(payload: TickPayload) -> dict:
    demo_time = datetime.now(IST).replace(hour=10, minute=30, second=0, microsecond=0) if cfg.broker == "paper" else None
    res = manager.on_tick(payload.symbol.upper(), payload.ltp, now_ist=demo_time)
    return {"result": res, "status": manager.status_dict()}


@app.post("/square-off/{symbol}")
def square_off_symbol(symbol: str, ltp: Optional[float] = None) -> dict:
    sym = symbol.upper()
    pos = manager.open_positions.get(sym)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"No open position for {sym}")
    px = ltp if ltp is not None else pos.ltp
    closed = manager.close_position(sym, px, "Manual Limit-Buffer Square Off")
    return {"closed": asdict(closed) if closed else None}


@app.post("/kill-switch")
def trigger_kill(payload: KillPayload) -> dict:
    closed = manager.kill_switch(payload.reason)
    return {"halted": manager.halted, "closed_count": len(closed)}
