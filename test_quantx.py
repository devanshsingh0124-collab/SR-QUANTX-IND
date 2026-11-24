""Automated verification test suite for INDIAN QUANTX (NSE Cash MIS)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import os
import tempfile

from broker_adapter import PaperBrokerAdapter
from config import QuantXConfig
from market_data import MarketSnapshot, generate_synthetic_ohlcv, passes_liquidity_gate, resample_timeframe
from smc_engine import TradeSignal, evaluate_signal
from tax_engine import calculate_mis_costs, calculate_net_pnl
from trade_manager import TradeManager

IST = timezone(timedelta(hours=5, minutes=30))


def test_liquidity_gate() -> None:
    cfg = QuantXConfig()
    good = MarketSnapshot("RELIANCE", 2940.0, 2939.8, 2940.2, 6500, 3500, 1800.0)
    ok, _ = passes_liquidity_gate(good, cfg)
    assert ok, "Liquid Nifty stock should pass gate"

    illiquid = MarketSnapshot("RELIANCE", 2940.0, 2939.8, 2940.2, 6500, 3500, 120.0)
    ok2, _ = passes_liquidity_gate(illiquid, cfg)
    assert not ok2, "Low turnover stock must be rejected"

    unknown = MarketSnapshot("PENNYSTK", 12.0, 11.9, 12.1, 100, 100, 600.0)
    ok3, _ = passes_liquidity_gate(unknown, cfg)
    assert not ok3, "Non-universe symbol must be rejected"


def test_2026_mis_tax_engine() -> None:
    gross, costs, net = calculate_net_pnl(1000.0, 1020.0, 100, "LONG", orders_executed=2)
    assert gross == 2000.0
    # Sell value = 102,000 => 0.025% STT = ₹25.50
    assert abs(costs.stt - 25.50) < 0.05, f"Unexpected STT: {costs.stt}"
    assert costs.brokerage <= 40.0, "Max ₹20/order across 2 orders"
    assert net == round(gross - costs.total, 2)


def test_marketable_limit_buffer_rounding() -> None:
    cfg = QuantXConfig()
    broker = PaperBrokerAdapter(cfg)
    buy_lim = broker.marketable_limit_price(2940.0, "BUY")
    sell_lim = broker.marketable_limit_price(2940.0, "SELL")
    assert buy_lim > 2940.0 and round(buy_lim * 20) == buy_lim * 20
    assert sell_lim < 2940.0 and round(sell_lim * 20) == sell_lim * 20


def test_50_30_20_profit_lock_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = QuantXConfig(capital=100000.0, db_path=os.path.join(tmp, "test.db"))
        broker = PaperBrokerAdapter(cfg)
        tm = TradeManager(cfg, broker)

        t_open = datetime(2026, 11, 24, 10, 0, tzinfo=IST)
        sig = TradeSignal(
            symbol="RELIANCE", side="LONG", entry_price=1000.0,
            stop_loss=990.0, risk_per_share=10.0, atr=5.7, adx=30.0,
            rvol=1.8, depth_imbalance=0.64, ema20_atr_dist=0.8,
            score=96, reason="Test A+ Setup",
        )
        pos = tm.open_trade(sig, now_ist=t_open)
        assert pos is not None
        assert pos.init_qty == 150, f"1.5% of 1L = 1500 / 10 = 150 sh, got {pos.init_qty}"

        # +0.75R risk slash
        tm.on_tick("RELIANCE", pos.entry_price + 8.0, now_ist=t_open + timedelta(minutes=5))
        assert pos.stage == 1 and pos.active_sl > pos.init_sl

        # TP1 (+1.25R) -> 50% booked + BE lock
        tm.on_tick("RELIANCE", pos.entry_price + 13.0, now_ist=t_open + timedelta(minutes=12))
        assert pos.stage == 2 and pos.rem_qty == 75 and pos.active_sl == pos.entry_price

        # TP2 (+2.30R) -> 30% booked (45 sh) + +1.45R trail
        tm.on_tick("RELIANCE", pos.entry_price + 23.5, now_ist=t_open + timedelta(minutes=25))
        assert pos.stage == 4 and pos.rem_qty == 30

        # TP3 (+3.50R) -> closes remaining 20% runner
        res = tm.on_tick("RELIANCE", pos.entry_price + 35.5, now_ist=t_open + timedelta(minutes=40))
        assert res == "TP3_HIT"
        assert "RELIANCE" not in tm.open_positions
        assert len(tm.closed_trades) == 1
        assert tm.closed_trades[0].net_pnl > 2500.0
        assert tm.profit_lock_active, "Profit-Lock should activate after >+2.5% net realized profit"


def test_stalled_loser_and_1512_auto_exit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = QuantXConfig(capital=100000.0, db_path=os.path.join(tmp, "test2.db"))
        tm = TradeManager(cfg, PaperBrokerAdapter(cfg))
        t_open = datetime(2026, 11, 24, 10, 0, tzinfo=IST)
        sig = TradeSignal(
            symbol="INFY", side="LONG", entry_price=1000.0, stop_loss=990.0,
            risk_per_share=10.0, atr=5.7, adx=25.0, rvol=1.5, depth_imbalance=0.6,
            ema20_atr_dist=0.9, score=90, reason="Test Stalled",
        )
        pos = tm.open_trade(sig, now_ist=t_open)
        assert pos is not None
        res = tm.on_tick("INFY", pos.entry_price - 6.0, now_ist=t_open + timedelta(minutes=46))
        assert res == "STALLED_CUT"

        # Test 15:12 IST auto-square-off
        sig2 = TradeSignal(
            symbol="SBIN", side="LONG", entry_price=800.0, stop_loss=792.0,
            risk_per_share=8.0, atr=4.5, adx=26.0, rvol=1.6, depth_imbalance=0.61,
            ema20_atr_dist=0.8, score=91, reason="Test EOD",
        )
        pos2 = tm.open_trade(sig2, now_ist=datetime(2026, 11, 24, 14, 0, tzinfo=IST))
        assert pos2 is not None
        res2 = tm.on_tick("SBIN", 802.0, now_ist=datetime(2026, 11, 24, 15, 12, tzinfo=IST))
        assert res2 == "AUTO_SQUARE_OFF" and tm.halted and len(tm.open_positions) == 0


def test_smc_engine_smoke() -> None:
    cfg = QuantXConfig()
    df_5m = generate_synthetic_ohlcv(2900.0, bars=80, trend="LONG", seed=7)
    df_15m = resample_timeframe(df_5m, 3)
    df_1h = resample_timeframe(df_5m, 6)
    ltp = float(df_5m.iloc[-1]["close"])
    snap = MarketSnapshot("RELIANCE", ltp, ltp - 0.05, ltp + 0.05, 6800, 3200, 1800.0)
    # Just verify evaluate_signal runs cleanly without error
    _ = evaluate_signal(snap, df_5m, df_15m, df_1h, cfg)


if __name__ == "__main__":
    test_liquidity_gate()
    test_2026_mis_tax_engine()
    test_marketable_limit_buffer_rounding()
    test_50_30_20_profit_lock_lifecycle()
    test_stalled_loser_and_1512_auto_exit()
    test_smc_engine_smoke()
    print("ALL INDIAN QUANTX TESTS PASSED!")
