# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SMTM-Lite is a lightweight cryptocurrency auto-trading system targeting the Bithumb (Korean) exchange. It runs in either simulation (paper trading) or live mode, selecting assets via a 4-filter statistical pipeline and executing parallel buy/sell trades via worker threads.

## Running the System

```bash
# Install dependencies (Python 3.11 required)
pip install -r requirements.txt

# Run in simulation mode (default)
python operator.py --mode sim --n 4 --budget 100000 --fee 0.04

# Run in live mode with DB persistence
python operator.py --mode live --save_db --n 6 --budget 500000

# Test WebSocket connection to Bithumb
python test.py

# Post-run analysis tools (require a completed DB run)
python analyze_selection.py
python analyze_candidates.py
```

## Environment Variables

Create a `.env` file with:
```
BITHUMB_CON_KEY=<api_key>
BITHUMB_SEC_KEY=<api_secret>
TELEGRAM_TOKEN=<bot_token>
TELEGRAM_CHAT_ID=<chat_id>
```

Telegram token and chat ID can also be passed as `--token` / `--chat_id` CLI args. `--msg no` disables Telegram entirely.

## Architecture

### Module Responsibilities

| Module | Role |
|--------|------|
| `operator.py` | Central orchestrator: main loop, argument parsing, Telegram async queue, circuit breaker (-5% cumulative loss → shutdown) |
| `data_provider.py` | WebSocket client (`wss://pubwss.bithumb.com/pub/ws`), auto-reconnect, optional SQLite write, exposes `latest_prices` dict |
| `strategy.py` | 4-filter pipeline → selects top-N tickers; filters: `price_rate > 0.1%`, `units_rate > 50%`, `volatility < 1%`, trend alignment (MA crossover) |
| `trader.py` | Spawns/manages Worker threads (one per open position, max `--n`); thread-safe via lock on worker dict |
| `analyzer.py` | Tracks trade history, asset snapshots, win/loss, fees; generates performance reports |
| `config.py` | Loads `.env` and returns authenticated `pybithumb` instance |

### Data Flow

```
Bithumb WebSocket
       ↓
DataProvider  →  latest_prices (dict)  →  SQLite (optional)
       ↓
Operator main loop (5s interval)
       ├─→ Strategy.update_data()  →  pocket (selected tickers)
       ├─→ Analyzer.put_asset_snapshot()  →  return_rate
       ├─→ circuit breaker check
       └─→ Trader.execute_trade() per free slot
                  ↓
           Worker thread (per ticker)
                  ├─→ BUY (slippage check: reject if >0.2% jump)
                  └─→ SELL loop (100ms intervals)
                         stop-loss: -0.2%
                         take-profit: +0.7%
                         trailing stop: +0.5% then -0.2% pullback
                         stagnation exit: 30s with <0.05% move
                         timeout: 60s max hold
```

### Threading Model

- **Main thread**: Operator loop + Strategy + circuit breaker
- **WebSocket thread**: DataProvider async event loop with reconnection
- **Worker threads**: One per active position (max `--n`)
- **Telegram thread**: Daemon thread with async queue for notifications

### Logging

- `log/smtm_YYYYMMDD_HHMMSS.log` — main system log (all modules)
- `log/pocket_YYYYMMDD_HHMMSS.log` — strategy selection detail log
- Rotation: 2 MB max, 5 backups; timezone: KST (UTC+9)
- In `sim` mode, strategy details are also written to the main log

### Database

SQLite file `smtm_data.db` (only created with `--save_db`). Single table `price_data` (timestamp, ticker, closing_price, units_traded). **Cleared on every restart.**
