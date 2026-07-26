@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==================================================
echo    Starting NavIC - Opportunity Intelligence
echo ==================================================
echo.

REM --- 1. Make sure Docker Desktop is running ---------------------------
docker info >nul 2>&1
if errorlevel 1 (
  echo [!] Docker Desktop does not look like it is running.
  echo.
  echo     Please open Docker Desktop, wait for the whale icon to stop
  echo     animating, then double-click this file again.
  echo.
  pause
  exit /b 1
)

REM --- 2. Build and start the app in the background ---------------------
echo Building and starting NavIC...
echo (The FIRST run downloads and builds images - this can take a few minutes.
echo  Later runs are fast.)
echo.
docker compose -f docker-compose.demo.yml up --build -d
if errorlevel 1 (
  echo.
  echo [!] Something went wrong while starting. See the messages above.
  echo.
  pause
  exit /b 1
)

REM --- 3. Wait until the app is ready ----------------------------------
echo.
echo Waiting for NavIC to be ready...
set /a tries=0
:wait
curl -s -o nul --fail http://localhost:8481/health
if not errorlevel 1 goto ready
set /a tries+=1
if !tries! GEQ 90 (
  echo     Taking longer than usual - opening anyway, just refresh in a moment.
  goto ready
)
timeout /t 2 >nul
goto wait

:ready
echo.
echo NavIC is ready. Opening http://localhost:8480 in your browser...
start "" http://localhost:8480
echo.
echo ------------------------------------------------------------------
echo   NavIC is now running (in Docker Desktop, in the background).
echo.
echo   - Open it any time at:      http://localhost:8480
echo   - To STOP it, double-click: stop-navic.bat
echo ------------------------------------------------------------------
echo.
echo You can close this window - NavIC keeps running until you stop it.
echo.
pause
