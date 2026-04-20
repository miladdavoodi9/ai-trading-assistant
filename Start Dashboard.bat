@echo off
cd /d "%~dp0"
echo Starting AI Trading Dashboard...
python parse_schwab.py
start "" http://localhost:8765
python dashboard.py
pause
