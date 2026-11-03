@echo off
cd /d "%~dp0\.."
py -3 desktop\wappai_hub.py
if errorlevel 1 pause
