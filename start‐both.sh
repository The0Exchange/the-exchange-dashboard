#!/usr/bin/env bash
# ─── start-both.sh ─────────────────────────────────────────────────────

# 1) Launch the pricing engine in the background (log output to pricing_engine.log)
python pricing_engine.py &> pricing_engine.log &

# 2) Wait 5 seconds so SQLite has time to create price_history.db and the history table
sleep 5

# 3) Replace this shell with Gunicorn bound to $PORT
exec gunicorn wsgi:server --bind 0.0.0.0:"${PORT}"
