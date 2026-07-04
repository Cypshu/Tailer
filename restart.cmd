@echo off
setlocal

cd /d "%~dp0"

echo Restarting TAILER services...
call "%~dp0stop.cmd"

timeout /t 2 /nobreak

call "%~dp0start.cmd"
echo TAILER restart complete!
exit /b %errorlevel%
