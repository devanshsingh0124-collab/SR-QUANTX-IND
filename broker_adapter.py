"""SEBI-2026-Compliant Broker Adapters (Paper, Angel One SmartAPI, DhanHQ v2)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
import time
import uuid

from config import QuantXConfig


@dataclass(frozen=True)
class OrderReceipt:
    order_id: str
    symbol: str
    side: str          # "BUY" | "SELL"
    qty: int
    limit_price: float
    fill_price: float
    status: str        # "FILLED" | "REJECTED"
    message: str


class RateLimiter:
    """Enforce client-side <10 OPS limit (NSE TOPS compliance)."""

    def __init__(self, max_ops: int = 8) -> None:
        self.max_ops = max(1, max_ops)
        self._timestamps: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) >= 1.0:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.max_ops:
            sleep_for = 1.0 - (now - self._timestamps[0]) + 0.01
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._timestamps.append(time.monotonic())


class BrokerAdapter(ABC):
    def __init__(self, cfg: QuantXConfig) -> None:
        self.cfg = cfg
        self.limiter = RateLimiter(cfg.max_ops_per_sec)

    def marketable_limit_price(self, ltp: float, side: str) -> float:
        """SEBI 2026 rule: never send raw MARKET orders; use ±0.10% LIMIT buffer."""
        buf = self.cfg.limit_buffer_pct
        raw = ltp * (1.0 + buf) if side.upper() == "BUY" else ltp * (1.0 - buf)
        # Round to NSE 0.05 tick size
        return round(round(raw * 20.0) / 20.0, 2)

    @abstractmethod
    def place_mis_limit_order(self, symbol: str, side: str, qty: int, ltp: float) -> OrderReceipt:
        raise NotImplementedError


class PaperBrokerAdapter(BrokerAdapter):
    """Zero-cost paper trading adapter with realistic 0.04% slippage simulation."""

    def place_mis_limit_order(self, symbol: str, side: str, qty: int, ltp: float) -> OrderReceipt:
        self.limiter.acquire()
        if qty <= 0 or ltp <= 0:
            return OrderReceipt("", symbol, side, qty, 0.0, 0.0, "REJECTED", "Invalid qty or LTP")
        limit_px = self.marketable_limit_price(ltp, side)
        slip = 0.0004
        fill_px = round(ltp * (1.0 + slip) if side.upper() == "BUY" else ltp * (1.0 - slip), 2)
        return OrderReceipt(
            order_id=f"PAPER-{uuid.uuid4().hex[:8].upper()}",
            symbol=symbol.upper(),
            side=side.upper(),
            qty=qty,
            limit_price=limit_px,
            fill_price=fill_px,
            status="FILLED",
            message="Simulated MIS Limit-Buffer fill",
        )


class AngelOneBrokerAdapter(BrokerAdapter):
    """Angel One SmartAPI adapter (Free Trading + Data, TOTP 2FA, Static IP)."""

    def __init__(self, cfg: QuantXConfig) -> None:
        super().__init__(cfg)
        self._client = None

    def login_totp(self) -> bool:
        try:
            import pyotp
            from SmartApi import SmartConnect
        except ImportError as exc:
            raise RuntimeError("Install smartapi-python and pyotp for Angel One live mode") from exc

        totp = pyotp.TOTP(self.cfg.angel_totp_secret).now()
        self._client = SmartConnect(api_key=self.cfg.angel_api_key)
        resp = self._client.generateSession(self.cfg.angel_client_id, self.cfg.angel_pin, totp)
        return bool(resp and resp.get("status"))

    def place_mis_limit_order(self, symbol: str, side: str, qty: int, ltp: float) -> OrderReceipt:
        self.limiter.acquire()
        limit_px = self.marketable_limit_price(ltp, side)
        if self._client is None:
            return OrderReceipt("", symbol, side, qty, limit_px, 0.0, "REJECTED", "Angel One session not initialized")
        payload = {
            "variety": "NORMAL",
            "tradingsymbol": f"{symbol.upper()}-EQ",
            "symboltoken": "",  # Populate from Angel OpenAPIScripMaster.json
            "transactiontype": side.upper(),
            "exchange": "NSE",
            "ordertype": "LIMIT",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": str(limit_px),
            "quantity": str(qty),
        }
        order_id = self._client.placeOrder(payload)
        return OrderReceipt(str(order_id), symbol.upper(), side.upper(), qty, limit_px, limit_px, "FILLED", "Submitted to Angel One")


class DhanHQBrokerAdapter(BrokerAdapter):
    """DhanHQ v2 adapter (Free Trading API, ₹499/mo 20-Level Depth, Static IP)."""

    def __init__(self, cfg: QuantXConfig) -> None:
        super().__init__(cfg)
        self._client = None

    def connect(self) -> bool:
        try:
            from dhanhq import dhanhq
        except ImportError as exc:
            raise RuntimeError("Install dhanhq package for DhanHQ live mode") from exc
        self._client = dhanhq(self.cfg.dhan_client_id, self.cfg.dhan_access_token)
        return True

    def place_mis_limit_order(self, symbol: str, side: str, qty: int, ltp: float) -> OrderReceipt:
        self.limiter.acquire()
        limit_px = self.marketable_limit_price(ltp, side)
        if self._client is None:
            return OrderReceipt("", symbol, side, qty, limit_px, 0.0, "REJECTED", "DhanHQ client not connected")
        resp = self._client.place_order(
            security_id="",  # Map from Dhan NSE scrip master CSV
            exchange_segment=self._client.NSE,
            transaction_type=self._client.BUY if side.upper() == "BUY" else self._client.SELL,
            quantity=qty,
            order_type=self._client.LIMIT,
            product_type=self._client.INTRA,
            price=limit_px,
        )
        oid = str(resp.get("data", {}).get("orderId", ""))
        status = "FILLED" if oid else "REJECTED"
        return OrderReceipt(oid, symbol.upper(), side.upper(), qty, limit_px, limit_px, status, str(resp))


def create_broker(cfg: QuantXConfig) -> BrokerAdapter:
    if cfg.broker == "angel":
        return AngelOneBrokerAdapter(cfg)
    if cfg.broker == "dhan":
        return DhanHQBrokerAdapter(cfg)
    return PaperBrokerAdapter(cfg)
