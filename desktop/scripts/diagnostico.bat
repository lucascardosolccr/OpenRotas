@echo off
REM OpenRotas Desktop — roda o autodiagnostico de recursos (bases, cache, motor local).
setlocal
cd /d "%~dp0\..\.."
if exist "venv\Scripts\python.exe" (
  venv\Scripts\python desktop\app\diagnostics.py
) else (
  python desktop\app\diagnostics.py
)
echo.
pause
endlocal
