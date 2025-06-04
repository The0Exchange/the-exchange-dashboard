#!/usr/bin/env bash
#
# start-both.sh  — run the pricing engine in the background, then start Flask

# 1) Launch the pricing engine in the background and capture its log:
python pricing_engine.py &> pricing_engine.log &

# 2) Give it a moment to create the DB and insert its first row (optional):
sleep 2

# 3) Now replace the shell with Gunicorn serving app.py via wsgi.py
exec gunicorn wsgi:server --bind 0.0.0.0:10000
