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
