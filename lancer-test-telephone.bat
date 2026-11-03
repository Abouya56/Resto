@echo off
chcp 65001 >nul
title Resto - test sur telephone
cd /d "%~dp0backend"

rem Trouve l'adresse du PC sur le Wi-Fi / le reseau local
set LAN_IP=
for /f %%i in ('powershell -NoProfile -Command "(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1).IPv4Address.IPAddress"') do set LAN_IP=%%i

if "%LAN_IP%"=="" (
    echo.
    echo  Pas de reseau trouve. Connectez ce PC au Wi-Fi puis relancez.
    pause
    exit /b 1
)

rem Les QR codes utilisent cette adresse : un telephone du meme Wi-Fi peut donc les ouvrir.
set SITE_URL=http://%LAN_IP%:8001

echo.
echo  ============================================================
echo   RESTO - TEST SUR TELEPHONE
echo  ============================================================
echo.
echo   1. Le telephone doit etre sur le MEME Wi-Fi que ce PC.
echo   2. Sur le telephone, ouvrez :   %SITE_URL%
echo   3. Pour tester un QR code : sur ce PC, ouvrez
echo      http://127.0.0.1:8001/gerant/tables/   puis cliquez sur
echo      "QR code" d'une table, et scannez-le avec l'appareil photo.
echo.
echo   Si Windows demande d'autoriser Python : cliquez "Autoriser".
echo   Pour arreter : fermez cette fenetre (ou Ctrl+C).
echo  ============================================================
echo.

"%~dp0.venv\Scripts\python.exe" manage.py refresh_qr_codes
echo.
"%~dp0.venv\Scripts\python.exe" manage.py runserver 0.0.0.0:8001
pause
