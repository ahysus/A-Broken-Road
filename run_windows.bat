@echo off
rem Starts the demo on Windows. Double-click this file, then open http://127.0.0.1:8000
rem Close this window to stop the server.
cd /d "%~dp0"
.venv\Scripts\python.exe src\app.py
pause
