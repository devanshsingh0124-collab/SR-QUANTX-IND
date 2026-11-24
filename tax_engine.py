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
