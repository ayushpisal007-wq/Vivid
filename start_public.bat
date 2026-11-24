@echo off
title Vivid
cd /d "%~dp0"
if not exist ".venv312\Scripts\python.exe" (
  echo Python environment .venv312 not found. See README.md, "Run it locally".
  pause
  exit /b 1
)
".venv312\Scripts\python.exe" tools\start_public.py
pause
