""08:55 AM IST Daily 2FA/TOTP Login & Readiness Check Cron Script."""
from __future__ import annotations

from dotenv import load_dotenv
from broker_adapter import AngelOneBrokerAdapter, DhanHQBrokerAdapter, create_broker
from config import load_config
from telegram_bot import TelegramNotifier


def main() -> None:
    load_dotenv()
    cfg = load_config()
    notifier = TelegramNotifier(cfg)
    broker = create_broker(cfg)

    if isinstance(broker, AngelOneBrokerAdapter):
        ok = broker.login_totp()
        msg = "Angel One TOTP login SUCCESS." if ok else "Angel One TOTP login FAILED!"
        notifier.send("LOGIN", msg)
        print(msg)
    elif isinstance(broker, DhanHQBrokerAdapter):
        ok = broker.connect()
        msg = "DhanHQ session READY." if ok else "DhanHQ connection FAILED!"
        notifier.send("LOGIN", msg)
        print(msg)
    else:
        msg = f"Paper mode active (Capital ₹{cfg.capital:,.0f}, Hard Exit {cfg.hard_exit_ist} IST)."
        notifier.send("LOGIN", msg)
        print(msg)


if __name__ == "__main__":
    main()
