#!/bin/bash
cd "$(dirname "$0")"
echo "Launching AI Trading Assistant..."
python3 parse_schwab.py
sleep 2 && open http://localhost:8765 &
python3 dashboard.py
