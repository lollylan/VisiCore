@echo off
title VisiCore
echo.
echo  =============================
echo   VisiCore wird gestartet...
echo  =============================
echo.
cd /d "%~dp0"
venv\Scripts\python.exe app.py
pause
