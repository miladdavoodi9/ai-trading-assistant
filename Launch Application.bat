@echo off
cd /d "%~dp0"
echo Launching AI Trading Assistant...
python parse_schwab.py
start "" http://localhost:8765
python dashboard.py
pause
