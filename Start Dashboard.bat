@echo off
cd /d "%~dp0"
echo Starting AI Trading Dashboard...
start "" http://localhost:8765
C:\Users\milad\anaconda3\python.exe dashboard.py
pause
