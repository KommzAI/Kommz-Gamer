@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0.."

echo ============================================================
echo  Kommz Gamer — CI/CD Build Script (GitHub Actions)
echo ============================================================
echo.

set "APP_VERSION=5.2"
if exist "version.txt" (
  for /f "usebackq delims=" %%v in (`powershell -NoProfile -Command "$v=(Get-Content -Raw 'version.txt').Trim(); $v -replace '[^0-9A-Za-z._-]',''"`) do set "APP_VERSION=%%v"
)

:: Detect edition from env (set by GitHub Actions matrix)
if "%KOMMZ_EDITION%"=="" set "KOMMZ_EDITION=community"
if /I "%KOMMZ_EDITION%"=="community" (
  set "EDITION_NAME=Community"
  set "KOMMZ_CLOUD_FEATURES=0"
) else (
  set "EDITION_NAME=Private"
  set "KOMMZ_CLOUD_FEATURES=1"
)

echo Edition: %EDITION_NAME%
echo Version: %APP_VERSION%
echo.

:: Install dependencies
echo [1/4] Installation des dependances Python...
pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo [ERREUR] pip install a echoue
  exit /b 1
)

:: Also install nuitka
pip install nuitka ordered-set zstandard --quiet

:: Rust stable for nuitka
echo [2/4] Nuitka build standalone...
set PYWEBVIEW_GUI=edgechromium
set KOMMZ_EDITION_PROFILE=%KOMMZ_EDITION%
set KOMMZ_CLOUD_FEATURES=%KOMMZ_CLOUD_FEATURES%
set KOMMZ_SETTINGS_FILE=settings.%KOMMZ_EDITION%.json

set "OUT_EXE=Kommz_Gamer_V%APP_VERSION%_%EDITION_NAME%_standalone.exe"

python -m nuitka vtp_core.py --standalone --assume-yes-for-downloads --jobs=2 --windows-console-mode=disable --enable-plugin=tk-inter --windows-icon-from-ico=icon.ico --include-data-dir=web=web --include-module=webview --include-module=webview.platforms.edgechromium --nofollow-import-to=webview.platforms.qt --nofollow-import-to=webview.platforms.gtk --nofollow-import-to=webview.platforms.cocoa --nofollow-import-to=webview.platforms.android --include-package=deepgram --include-package=deepl --include-package=deep_translator --include-package=miniaudio --include-package=soundfile --include-package=sounddevice --include-package=keyboard --include-package=flask --include-package=flask_cors --include-package=ftfy --include-package=lingua --include-package=unidecode --include-package=qrcode --include-package=psutil --noinclude-pytest-mode=nofollow --noinclude-setuptools-mode=nofollow

if errorlevel 1 (
  echo [ERREUR] Build Nuitka a echoue
  exit /b 1
)

:: Copy settings file
if exist "%KOMMZ_SETTINGS_FILE%" copy /y "%KOMMZ_SETTINGS_FILE%" "vtp_core.dist\settings.json" >nul

:: Rename exe
if exist "vtp_core.dist\vtp_core.exe" (
  ren "vtp_core.dist\vtp_core.exe" "%OUT_EXE%" 2>nul
)

:: Build portable ZIP
echo [3/4] Creation du ZIP portable...
set "ZIP_NAME=Kommz_Gamer_V%APP_VERSION%_%EDITION_NAME%_Portable.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'vtp_core.dist\*' -DestinationPath '%ZIP_NAME%' -Force"

:: Upload artifacts path
echo [4/4] Build termine.
echo EXE: vtp_core.dist\%OUT_EXE%
echo ZIP: %ZIP_NAME%

:: Write artifact paths for GitHub Actions
echo exe_path=vtp_core.dist\%OUT_EXE%> ci_artifact_paths.txt
echo zip_path=%ZIP_NAME%>> ci_artifact_paths.txt

exit /b 0
