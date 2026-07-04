@echo off
setlocal

cd /d "%~dp0"

echo Stopping TAILER services...
docker compose down
echo Services stopped successfully!
exit /b 0
