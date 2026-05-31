#!/bin/bash
cd ~/sr-levels
while true; do
    python3 scripts/app.py >> ~/sr-levels/flask.log 2>&1
    echo "[$(date)] Flask exited, restarting in 5s..." >> ~/sr-levels/flask.log
    sleep 5
done
