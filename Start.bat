@echo off
cd /d "%~dp0"
python video_downloader.py
if errorlevel 1 pause
