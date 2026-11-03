@echo off
chcp 65001 >nul
title Resto - test avec un ami (tunnel)
echo.
echo  ============================================================
echo   RESTO - TEST A DISTANCE (n'importe quel reseau)
echo  ============================================================
echo.
echo   1. Dans une 1re fenetre, lancez le site :  lancer-test-telephone.bat
echo   2. Ici, un tunnel va donner une adresse du type :
echo         https://quelquechose.trycloudflare.com
echo      Copiez-la et envoyez-la a votre ami.
echo   3. Sur CE PC, ouvrez cette meme adresse pour voir les QR codes
echo      (page Tables du gerant) : ils utiliseront l'adresse du tunnel.
echo   4. L'adresse change a chaque lancement. Fermez cette fenetre pour couper l'acces.
echo  ============================================================
echo.
"%ProgramFiles(x86)%\cloudflared\cloudflared.exe" tunnel --url http://localhost:8001
if errorlevel 1 cloudflared tunnel --url http://localhost:8001
pause
