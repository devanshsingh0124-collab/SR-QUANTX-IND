"""QuantX-style Telegram Alert Dispatcher for INDIAN QUANTX."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List
import urllib.request
import urllib.parse
import json

from config import QuantXConfig

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class TelegramNotifier:
    cfg: QuantXConfig
    history: List[dict] = field(default_factory=list)

    def send(self, tag: str, message: str) -> bool:
        ts = datetime.now(IST).strftime("%H:%M:%S IST")
        record = {"time": ts, "tag": tag, "text": message}
        self.history.insert(0, record)
        if len(self.history) > 50:
            self.history.pop()

        if not self.cfg.telegram_bot_token or not self.cfg.telegram_chat_id:
            return False

        url = f"https://api.telegram.org/bot{self.cfg.telegram_bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.cfg.telegram_chat_id,
            "text": f"[{tag}] {message}\n({ts})",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False
