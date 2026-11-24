# INDIAN QUANTX — NSE Cash MIS Algorithmic Trading System

SR QuantX (`btc-live-terminal`) ke proven **SMC + 50/30/20 Smart Profit-Lock** engine ko Indian stock market (NSE Cash Intraday MIS) aur **1 April 2026 SEBI retail algo compliance** ke hisaab se design kiya gaya production codebase.

## Core Architecture & SEBI 2026 Compliance

- **Static IP Ready**: Render dynamic IP ki jagah Mumbai region Static-IP VPS (AWS Lightsail / DigitalOcean / Oracle) par deploy karein aur broker portal par IP whitelist karein ([NSE/INVG/67858](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf), [FYERS SEBI Rules Guide](https://support.fyers.in/portal/en/kb/articles/what-are-the-new-sebi-rules-for-retail-algo-trading-from-april-01-2026)).
- **Zero Market Orders**: `broker_adapter.py` har order ko **Marketable Limit Order (`LTP ± 0.10%`)** banakar 0.05 tick par round karta hai aur client-side `< 8 OPS` rate limiter lagata hai (NSE ke 10 OPS TOPS threshold ke neeche).
- **Exact 2026 MIS Tax Engine**: `tax_engine.py` har trade par ₹20/order cap brokerage, `0.025%` sell-side STT ([VRDNation STT 2026](https://www.vrdnation.com/stt-cash-fno-intraday/)), NSE txn fee, SEBI fee, stamp duty, aur 18% GST deduct karke real Net P&L calculate karta hai.
- **50/30/20 Profit-Lock Engine**: `+0.75R` risk slash (-0.5R), `TP1 +1.25R` (50% book + Breakeven), `+1.75R` (+0.90R trail), `TP2 +2.30R` (30% book + 1.45R trail), `+2.90R` (+2.20R ratchet), `TP3 +3.50R` (20% runner), `45-min` stalled-loser cut, aur `15:12 IST` mandatory auto-square-off.

## Quick Start (Local ya Mumbai VPS)

```bash
# 1. Unzip aur folder mein jayein
unzip indian_quantx.zip
cd indian_quantx

# 2. Virtual environment aur packages install karein
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Environment setup karein (default: paper mode, ₹1,00,000 capital)
cp .env.example .env

# 4. Automated tests aur dry-run verify karein
python3 test_quantx.py

# 5. FastAPI backend start karein
uvicorn server:app --host 0.0.0.0 --port 8000

# 6. Dusre terminal mein mobile-first Streamlit dashboard start karein
streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
```

## Daily 08:55 AM IST Auto-Login Cron (Linux VPS)

```cron
55 8 * * 1-5 cd /home/ubuntu/indian_quantx && /home/ubuntu/indian_quantx/.venv/bin/python daily_login.py >> logs/login.log 2>&1
```

## Live Broker Activation Checklist

1. **Angel One SmartAPI** ([Docs](https://smartapi.angelbroking.com/)): Free Trading + Free Data; `.env` mein `QUANTX_BROKER=angel` aur API Key, Client ID, PIN, TOTP Secret bharein aur apna VPS Static IP whitelist karein.
2. **DhanHQ v2** ([Pricing](https://docs.dhanhq.co/pricing)): Free Trading API + ₹499/mo 20-Level Depth Data; `.env` mein `QUANTX_BROKER=dhan`, `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` bharein aur Static IP whitelist karein.
3. Live jaane se pehle kam se kam **15 trading sessions Paper Mode** mein chalakar slippage, net post-STT expectancy aur 15:12 IST auto-exit verify karein.
