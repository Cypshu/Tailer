@echo off
setlocal EnableExtensions

for %%I in ("%~dp0.") do set "PROJECT_DIR=%%~fI"
set "COMPOSE_FILE=%~dp0docker-compose.yml"
if not defined TAILER_COMPOSE_WAIT_TIMEOUT set "TAILER_COMPOSE_WAIT_TIMEOUT=300"
if not defined TAILER_COMPOSE_LOG_TAIL set "TAILER_COMPOSE_LOG_TAIL=200"

if "%~1"=="" goto menu
if /i "%~1"=="start" goto start
if /i "%~1"=="stop" goto stop
if /i "%~1"=="restart" goto restart
if /i "%~1"=="status" goto status
if /i "%~1"=="logs" goto logs
if /i "%~1"=="config" goto config
if /i "%~1"=="help" goto help
if /i "%~1"=="-h" goto help
if /i "%~1"=="--help" goto help

echo Unknown command: %~1 1>&2
echo. 1>&2
goto help_error

:start
call :require_compose
if errorlevel 1 exit /b %errorlevel%
call :start_stack
exit /b %errorlevel%

:stop
call :require_compose
if errorlevel 1 exit /b %errorlevel%
call :stop_stack
exit /b %errorlevel%

:restart
call :require_compose
if errorlevel 1 exit /b %errorlevel%
call :stop_stack
if errorlevel 1 exit /b %errorlevel%
call :start_stack
exit /b %errorlevel%

:status
call :require_compose
if errorlevel 1 exit /b %errorlevel%
docker compose --project-directory "%PROJECT_DIR%" --file "%COMPOSE_FILE%" ps %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:logs
call :require_compose
if errorlevel 1 exit /b %errorlevel%
docker compose --project-directory "%PROJECT_DIR%" --file "%COMPOSE_FILE%" logs --follow --tail "%TAILER_COMPOSE_LOG_TAIL%" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:config
call :require_compose
if errorlevel 1 exit /b %errorlevel%
docker compose --project-directory "%PROJECT_DIR%" --file "%COMPOSE_FILE%" config --quiet
if errorlevel 1 exit /b %errorlevel%
echo Compose configuration is valid.
exit /b 0

:start_stack
call :ensure_environment
if errorlevel 1 exit /b %errorlevel%
docker compose --project-directory "%PROJECT_DIR%" --file "%COMPOSE_FILE%" up --build --detach --wait --wait-timeout "%TAILER_COMPOSE_WAIT_TIMEOUT%"
if errorlevel 1 exit /b %errorlevel%
docker compose --project-directory "%PROJECT_DIR%" --file "%COMPOSE_FILE%" ps
exit /b %errorlevel%

:stop_stack
docker compose --project-directory "%PROJECT_DIR%" --file "%COMPOSE_FILE%" down
exit /b %errorlevel%

:ensure_environment
if exist "%PROJECT_DIR%\.env" exit /b 0
if not exist "%PROJECT_DIR%\.env.example" exit /b 0
copy /Y "%PROJECT_DIR%\.env.example" "%PROJECT_DIR%\.env" >nul
if errorlevel 1 exit /b %errorlevel%
echo Created %PROJECT_DIR%\.env from .env.example
exit /b 0

:require_compose
where docker >nul 2>&1
if errorlevel 1 (
  echo TAILER: Docker is not installed or is not on PATH. 1>&2
  exit /b 1
)
docker compose version >nul 2>&1
if errorlevel 1 (
  echo TAILER: Docker Compose v2 is not available. 1>&2
  exit /b 1
)
exit /b 0

:menu
cls
echo TAILER service control
echo.
echo   1. Start
echo   2. Stop
echo   3. Restart
echo   4. Status
echo   5. Logs
echo   6. Validate configuration
echo   0. Exit
echo.
choice /C 1234560 /N /M "Select an action: "
if errorlevel 7 exit /b 0
if errorlevel 6 goto menu_config
if errorlevel 5 goto menu_logs
if errorlevel 4 goto menu_status
if errorlevel 3 goto menu_restart
if errorlevel 2 goto menu_stop
if errorlevel 1 goto menu_start
goto menu

:menu_start
call "%~f0" start
goto menu_pause

:menu_stop
call "%~f0" stop
goto menu_pause

:menu_restart
call "%~f0" restart
goto menu_pause

:menu_status
call "%~f0" status
goto menu_pause

:menu_logs
echo Press Ctrl+C to stop following logs and return to the menu.
call "%~f0" logs
goto menu_pause

:menu_config
call "%~f0" config

:menu_pause
echo.
pause
goto menu

:help
call :print_help
exit /b 0

:help_error
call :print_help 1>&2
exit /b 2

:print_help
echo Usage: %~nx0 ^<command^> [service...]
echo.
echo Commands:
echo   start       Build and start the stack, then wait for healthy services
echo   stop        Stop the stack and remove its containers and network
echo   restart     Stop, rebuild, and start the complete stack
echo   status      Show Compose service status; optionally limit to services
echo   logs        Follow recent logs; optionally limit to services
echo   config      Validate the rendered Compose configuration
echo   help        Show this help
echo.
echo Environment:
echo   TAILER_COMPOSE_WAIT_TIMEOUT  Startup health timeout in seconds ^(default: 300^)
echo   TAILER_COMPOSE_LOG_TAIL      Lines shown before following logs ^(default: 200^)
exit /b 0
