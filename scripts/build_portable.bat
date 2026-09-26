@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0.."

echo.
echo ============================================
echo  Kommz Gamer V5.2 — Build Portable ZIP
echo ============================================
echo.

set "APP_VERSION=5.2"
if exist "version.txt" (
  for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "$v=(Get-Content -Raw 'version.txt').Trim(); $v -replace '[^0-9A-Za-z._-]',''"`) do set "APP_VERSION=%%v"
)

set "EDITION=%1"
if "%EDITION%"=="" set "EDITION=community"
if /I "%EDITION%"=="community" (
  set "EDITION_NAME=Community"
  set "DIST_DIR=dist_standalone\vtp_core.dist"
) else if /I "%EDITION%"=="private" (
  set "EDITION_NAME=Private"
  set "DIST_DIR=dist_standalone\vtp_core.dist"
) else (
  echo [ERREUR] Edition inconnue: %EDITION%. Utiliser community ou private.
  exit /b 1
)

if not exist "%DIST_DIR%\vtp_core.exe" (
  echo [ERREUR] Build standalone introuvable. Lancer d'abord run_standalone_build_%EDITION%.bat
  exit /b 1
)

set "ZIP_NAME=Kommz_Gamer_V%APP_VERSION%_%EDITION_NAME%_Portable.zip"
set "ZIP_TEMP=dist_standalone\Kommz_Gamer_Portable"

if exist "%ZIP_TEMP%" rmdir /s /q "%ZIP_TEMP%"
if exist "dist_standalone\%ZIP_NAME%" del /q "dist_standalone\%ZIP_NAME%"

echo Copie du build portable...
xcopy /e /i /q /y "%DIST_DIR%" "%ZIP_TEMP%"

:: Ajout d'un README dans le zip
(
echo Kommz Gamer V%APP_VERSION% — Edition %EDITION_NAME% Portable
echo ==========================================================
echo.
echo Aucune installation requise.
echo Double-cliquez sur vtp_core.exe pour lancer.
echo.
echo Support : https://github.com/Kommz-Gamer/Kommz-Gamer
echo Discord  : https://discord.gg/kommzgamer
echo.
) > "%ZIP_TEMP%\README_PORTABLE.txt"

echo Creation du ZIP portable...
powershell -NoProfile -Command "Compress-Archive -Path '%ZIP_TEMP%\*' -DestinationPath 'dist_standalone\%ZIP_NAME%' -Force"

if exist "%ZIP_TEMP%" rmdir /s /q "%ZIP_TEMP%"

echo.
echo ============================================
echo  ZIP portable cree :
echo  dist_standalone\%ZIP_NAME%
echo ============================================
exit /b 0
