#!/usr/bin/env bash
# ─── start-both.sh ─────────────────────────────────────────────────────

# 1) Launch the pricing engine in the background (log output to pricing_engine.log)
python pricing_engine.py &> pricing_engine.log &

# 2) Wait a moment for SQLite to initialize
sleep 2

# 3) Replace this shell with Gunicorn bound to $PORT
exec gunicorn wsgi:server --bind 0.0.0.0:"${PORT}"
