@echo off
setlocal

cd /d "%~dp0"

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo Created .env from .env.example
  )
)

echo Starting TAILER services...
docker compose up --build -d
if errorlevel 1 exit /b %errorlevel%

echo Services started successfully!
docker compose ps
exit /b %errorlevel%
