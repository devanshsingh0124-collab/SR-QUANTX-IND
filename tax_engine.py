"""QuantX 50/30/20 Smart Profit-Lock Trade Manager + SQLite State Persistence."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import math
import sqlite3
from typing import Dict, List, Optional
import uuid

from broker_adapter import BrokerAdapter
from config import QuantXConfig
from smc_engine import TradeSignal
from tax_engine import calculate_net_pnl
from telegram_bot import TelegramNotifier

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class OpenPosition:
    trade_id: str
    symbol: str
    side: str              # "LONG" | "SHORT"
    entry_price: float
    ltp: float
    init_sl: float
    active_sl: float
    risk_per_share: float
    init_qty: int
    rem_qty: int
    stage: int             # 0=init, 1=+0.75R, 2=TP1(50%+BE), 3=+1.75R, 4=TP2(30%+1.45R), 5=+2.90R
    realized_gross: float
    orders_used: int
    score: int
    opened_at_iso: str
    setup: str


@dataclass
class ClosedTrade:
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    qty: int
    gross_pnl: float
    total_costs: float
    net_pnl: float
    reason: str
    closed_at_iso: str


class TradeManager:
    """Manages sizing, 50/30/20 partial booking, trailing SL, Profit-Lock, & 15:12 exit."""

    def __init__(
        self,
        cfg: QuantXConfig,
        broker: BrokerAdapter,
        notifier: Optional[TelegramNotifier] = None,
    ) -> None:
        self.cfg = cfg
        self.broker = broker
        self.notifier = notifier or TelegramNotifier(cfg)
        self.open_positions: Dict[str, OpenPosition] = {}
        self.closed_trades: List[ClosedTrade] = []
        self.daily_trades_count: int = 0
        self.halted: bool = False
        self.halt_reason: str = ""
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.cfg.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS closed_trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT, side TEXT,
                    entry_price REAL, exit_price REAL, qty INTEGER,
                    gross_pnl REAL, total_costs REAL, net_pnl REAL,
                    reason TEXT, closed_at_iso TEXT
                )
                """
            )
            conn.commit()

    def _save_closed(self, c: ClosedTrade) -> None:
        with sqlite3.connect(self.cfg.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO closed_trades
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.trade_id, c.symbol, c.side, c.entry_price, c.exit_price,
                    c.qty, c.gross_pnl, c.total_costs, c.net_pnl, c.reason, c.closed_at_iso,
                ),
            )
            conn.commit()

    @property
    def realized_net_pnl(self) -> float:
        partial_gross = sum(p.realized_gross for p in self.open_positions.values())
        closed_net = sum(c.net_pnl for c in self.closed_trades)
        return round(closed_net + partial_gross, 2)

    @property
    def profit_lock_active(self) -> bool:
        return self.realized_net_pnl >= (self.cfg.capital * self.cfg.profit_lock_trigger_pct)

    def calculate_position_size(self, signal: TradeSignal) -> int:
        base_risk_pct = self.cfg.a_plus_risk_pct if signal.score >= 95 else self.cfg.risk_pct
        if self.profit_lock_active:
            base_risk_pct *= self.cfg.profit_lock_risk_mult

        risk_inr = self.cfg.capital * base_risk_pct
        qty_by_risk = math.floor(risk_inr / signal.risk_per_share) if signal.risk_per_share > 0 else 0
        safe_bp = self.cfg.capital * self.cfg.mis_leverage * self.cfg.safe_bp_ratio
        qty_by_bp = math.floor(safe_bp / signal.entry_price) if signal.entry_price > 0 else 0
        return max(0, min(qty_by_risk, qty_by_bp))

    def can_open_trade(self, signal: TradeSignal, now_ist: Optional[datetime] = None) -> tuple[bool, str]:
        if self.halted:
            return False, f"Engine halted: {self.halt_reason}"
        now = now_ist or datetime.now(IST)
        hhmm = now.strftime("%H:%M")
        if hhmm < self.cfg.entry_start_ist or hhmm > self.cfg.entry_cutoff_ist:
            return False, f"Outside NSE entry window ({self.cfg.entry_start_ist}-{self.cfg.entry_cutoff_ist} IST)"
        if len(self.open_positions) >= self.cfg.max_open_trades:
            return False, f"Max open trades ({self.cfg.max_open_trades}) reached"
        if self.daily_trades_count >= self.cfg.max_daily_trades:
            return False, f"Max daily trades ({self.cfg.max_daily_trades}) reached"
        if signal.symbol in self.open_positions:
            return False, f"{signal.symbol} already open"
        if self.profit_lock_active and signal.score < self.cfg.profit_lock_min_score:
            return False, f"Profit-Lock active: requires A+ score >= {self.cfg.profit_lock_min_score}"
        return True, "OK"

    def open_trade(self, signal: TradeSignal, now_ist: Optional[datetime] = None) -> Optional[OpenPosition]:
        ok, _ = self.can_open_trade(signal, now_ist=now_ist)
        if not ok:
            return None
        qty = self.calculate_position_size(signal)
        if qty <= 0:
            return None

        order_side = "BUY" if signal.side == "LONG" else "SELL"
        receipt = self.broker.place_mis_limit_order(signal.symbol, order_side, qty, signal.entry_price)
        if receipt.status != "FILLED":
            return None

        now = now_ist or datetime.now(IST)
        pos = OpenPosition(
            trade_id=f"QX-{uuid.uuid4().hex[:6].upper()}",
            symbol=signal.symbol,
            side=signal.side,
            entry_price=receipt.fill_price,
            ltp=receipt.fill_price,
            init_sl=signal.stop_loss,
            active_sl=signal.stop_loss,
            risk_per_share=signal.risk_per_share,
            init_qty=qty,
            rem_qty=qty,
            stage=0,
            realized_gross=0.0,
            orders_used=1,
            score=signal.score,
            opened_at_iso=now.isoformat(),
            setup=signal.reason,
        )
        self.open_positions[signal.symbol] = pos
        self.daily_trades_count += 1
        self.notifier.send(
            "ENTRY",
            f"{pos.symbol} {pos.side} · Qty {qty} @ ₹{pos.entry_price:.2f} · SL ₹{pos.active_sl:.2f} (Score {pos.score})",
        )
        return pos

    def _partial_book(self, pos: OpenPosition, fraction: float, ltp: float, label: str) -> int:
        target_qty = max(1, math.floor(pos.init_qty * fraction))
        book_qty = min(target_qty, pos.rem_qty)
        if book_qty <= 0:
            return 0
        exit_side = "SELL" if pos.side == "LONG" else "BUY"
        receipt = self.broker.place_mis_limit_order(pos.symbol, exit_side, book_qty, ltp)
        if receipt.status != "FILLED":
            return 0
        diff = (receipt.fill_price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - receipt.fill_price)
        pos.rem_qty -= book_qty
        pos.realized_gross = round(pos.realized_gross + diff * book_qty, 2)
        pos.orders_used += 1
        self.notifier.send(label, f"{pos.symbol} {pos.side} · Booked {book_qty} sh @ ₹{receipt.fill_price:.2f}")
        return book_qty

    def close_position(self, symbol: str, ltp: float, reason: str, now_ist: Optional[datetime] = None) -> Optional[ClosedTrade]:
        pos = self.open_positions.pop(symbol, None)
        if pos is None:
            return None

        fill_px = ltp
        if pos.rem_qty > 0:
            exit_side = "SELL" if pos.side == "LONG" else "BUY"
            receipt = self.broker.place_mis_limit_order(pos.symbol, exit_side, pos.rem_qty, ltp)
            fill_px = receipt.fill_price if receipt.status == "FILLED" else ltp
            pos.orders_used += 1

        rem_diff = (fill_px - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - fill_px)
        total_gross = round(pos.realized_gross + rem_diff * pos.rem_qty, 2)
        _, costs, _ = calculate_net_pnl(pos.entry_price, fill_px, pos.init_qty, pos.side, pos.orders_used)
        net_pnl = round(total_gross - costs.total, 2)

        now = now_ist or datetime.now(IST)
        closed = ClosedTrade(
            trade_id=pos.trade_id,
            symbol=pos.symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=fill_px,
            qty=pos.init_qty,
            gross_pnl=total_gross,
            total_costs=costs.total,
            net_pnl=net_pnl,
            reason=reason,
            closed_at_iso=now.isoformat(),
        )
        self.closed_trades.insert(0, closed)
        self._save_closed(closed)
        self.notifier.send(
            "EXIT",
            f"{closed.symbol} {closed.side} · {reason} · Net ₹{closed.net_pnl:+.2f} (Costs ₹{closed.total_costs:.2f})",
        )

        # Daily loss circuit breaker check
        if self.realized_net_pnl <= -(self.cfg.capital * self.cfg.max_daily_loss_pct) and not self.halted:
            self.kill_switch("DAILY LOSS CIRCUIT BREAKER (-2.5%)", {s: p.ltp for s, p in self.open_positions.items()}, now)
        return closed

    def on_tick(self, symbol: str, ltp: float, now_ist: Optional[datetime] = None) -> Optional[str]:
        """Process live price tick through the 50/30/20 Profit-Lock R-ladder."""
        now = now_ist or datetime.now(IST)
        if now.strftime("%H:%M") >= self.cfg.hard_exit_ist and self.open_positions:
            self.kill_switch("15:12 IST AUTO-SQUARE-OFF", {symbol: ltp}, now)
            return "AUTO_SQUARE_OFF"

        pos = self.open_positions.get(symbol)
        if pos is None:
            return None
        pos.ltp = ltp

        # 1. Stop-loss check
        if (pos.side == "LONG" and ltp <= pos.active_sl) or (pos.side == "SHORT" and ltp >= pos.active_sl):
            reason = "Trailing SL Hit (Profit Locked)" if pos.stage >= 2 else "Anti-Wick SL Hit"
            self.close_position(symbol, ltp, reason, now)
            return "SL_HIT"

        diff = (ltp - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - ltp)
        r_mult = diff / pos.risk_per_share if pos.risk_per_share > 0 else 0.0
        sign = 1.0 if pos.side == "LONG" else -1.0

        # 2. +0.75R -> Slash risk by 50%
        if pos.stage < 1 and r_mult >= self.cfg.r_risk_slash:
            pos.stage = 1
            pos.active_sl = round(pos.entry_price - sign * (0.50 * pos.risk_per_share), 2)
            self.notifier.send("SL", f"{symbol} +0.75R · Risk slashed 50%, SL -> ₹{pos.active_sl:.2f}")

        # 3. TP1 (+1.25R) -> Book 50% + Breakeven lock
        if pos.stage < 2 and r_mult >= self.cfg.r_tp1:
            pos.stage = 2
            self._partial_book(pos, 0.50, ltp, "TP1")
            pos.active_sl = pos.entry_price

        # 4. +1.75R -> Trail SL to +0.90R
        if pos.stage < 3 and r_mult >= self.cfg.r_trail_mid:
            pos.stage = 3
            pos.active_sl = round(pos.entry_price + sign * (0.90 * pos.risk_per_share), 2)

        # 5. TP2 (+2.30R) -> Book 30% (if capital >= 25k) or trail runner only (if < 25k to save brokerage)
        if pos.stage < 4 and r_mult >= self.cfg.r_tp2:
            pos.stage = 4
            if self.cfg.capital >= 25000.0:
                self._partial_book(pos, 0.30, ltp, "TP2")
            pos.active_sl = round(pos.entry_price + sign * (1.45 * pos.risk_per_share), 2)

        # 6. +2.90R -> Ratchet SL to +2.20R
        if pos.stage < 5 and r_mult >= self.cfg.r_trail_high:
            pos.stage = 5
            pos.active_sl = round(pos.entry_price + sign * (2.20 * pos.risk_per_share), 2)

        # 7. TP3 (+3.50R) -> Close remaining 20% runner
        if r_mult >= self.cfg.r_tp3:
            self.close_position(symbol, ltp, "TP3 Runner Hit (+3.50R)", now)
            return "TP3_HIT"

        # 8. 45-minute stalled-loser cut
        opened_dt = datetime.fromisoformat(pos.opened_at_iso)
        elapsed_min = (now - opened_dt).total_seconds() / 60.0
        if elapsed_min >= self.cfg.stalled_loser_minutes and r_mult <= self.cfg.stalled_loser_r:
            self.close_position(symbol, ltp, "45m Stalled-Loser Rule Cut", now)
            return "STALLED_CUT"

        return "UPDATED"

    def kill_switch(
        self,
        reason: str,
        ltp_map: Optional[Dict[str, float]] = None,
        now_ist: Optional[datetime] = None,
    ) -> List[ClosedTrade]:
        self.halted = True
        self.halt_reason = reason
        prices = ltp_map or {}
        closed = []
        for sym in list(self.open_positions.keys()):
            px = prices.get(sym, self.open_positions[sym].ltp)
            res = self.close_position(sym, px, reason, now_ist)
            if res:
                closed.append(res)
        self.notifier.send("HALT", f"{reason} · Closed {len(closed)} positions.")
        return closed

    def status_dict(self) -> dict:
        return {
            "broker": self.cfg.broker,
            "capital": self.cfg.capital,
            "buying_power_5x": self.cfg.capital * self.cfg.mis_leverage,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "profit_lock_active": self.profit_lock_active,
            "realized_net_pnl": self.realized_net_pnl,
            "daily_trades_count": self.daily_trades_count,
            "max_daily_trades": self.cfg.max_daily_trades,
            "open_positions": [asdict(p) for p in self.open_positions.values()],
            "closed_trades": [asdict(c) for c in self.closed_trades[:20]],
            "alerts": self.notifier.history[:20],
        }
