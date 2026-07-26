@echo off
cd /d "%~dp0"

echo ==================================================
echo    Stopping NavIC
echo ==================================================
echo.

docker compose -f docker-compose.demo.yml down

echo.
echo NavIC has been stopped. Double-click start-navic.bat to run it again.
echo.
pause
