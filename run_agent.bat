@echo off
rem Runs the Founder Follow-up Agent. Used by the daily scheduled task.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    python main.py
)
