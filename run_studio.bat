@echo off
title Locket Custom Studio
echo ===================================================
echo     🚀 KHOI DONG LOCKET CUSTOM STUDIO
echo     - Video sieu dai 2 - 5 Phut (Apple HEVC <6MB)
echo     - Khung anh doc quyen (Retro, Polaroid, Cyber)
echo     - Card Thoi tiet & Live Radar kinh mo
echo ===================================================
echo.
cd /d "%~dp0"
python web_studio\server.py
pause
