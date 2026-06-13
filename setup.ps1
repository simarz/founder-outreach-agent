# One-time setup: create a virtual environment and install dependencies.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "Creating virtual environment (.venv)..."
python -m venv .venv

Write-Host "Installing dependencies..."
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next: place your credentials.json here, then run:  .\.venv\Scripts\python.exe main.py"
