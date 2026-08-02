@echo off
setlocal

cd /d "%~dp0"

if not exist ".env" (
  if exist ".env.example" (
    copy /Y ".env.example" ".env" >nul
    echo Created .env from .env.example
  )
)

docker compose up --build -d
if errorlevel 1 exit /b %errorlevel%

docker compose ps
exit /b %errorlevel%
