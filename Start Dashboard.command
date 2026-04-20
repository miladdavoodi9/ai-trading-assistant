#!/bin/bash
cd "$(dirname "$0")"
echo "Starting AI Trading Dashboard..."
python3 parse_schwab.py
sleep 2 && open http://localhost:8765 &
python3 dashboard.py
