@echo off
setlocal
echo ============================================================
echo  Kommz Gamer — Code Signing (EV Certificate)
echo ============================================================
echo.
echo PRE-REQUIS:
echo   1. Acheter un certificat EV Code Signing (DigiCert, Sectigo...)
echo   2. Installer le token USB / HSM fourni
echo   3. signtool.exe doit etre dans le PATH
echo      (inclus dans Windows SDK ou Visual Studio Build Tools)
echo.
echo USAGE:
echo   scripts\sign_release.bat [exe_path]
echo.
echo EXEMPLE:
echo   scripts\sign_release.bat dist_standalone\Kommz_Gamer_V5.2_Community_standalone.exe
echo.

if "%1"=="" (
  echo [INFO] Aucun fichier specifie. Signer tous les .exe du dossier dist_standalone...
  for %%f in (dist_standalone\*.exe) do call :sign "%%f"
  goto :done
)

:sign
set "FILE=%~1"
if not exist "%FILE%" (
  echo [ERREUR] Fichier introuvable: %FILE%
  exit /b 1
)

echo Signature de %FILE%...

:: Option 1 : Certificat sur token USB (le plus courant pour EV)
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a "%FILE%"

:: Option 2 : Certificat fichier .pfx (pour CI/CD, stocke dans les secrets GitHub)
:: signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f certificate.pfx /p %CERT_PASSWORD% "%FILE%"

if errorlevel 1 (
  echo [ATTENTION] La signature a echoue. Verifiez votre certificat EV.
  echo L'application reste fonctionnelle, mais SmartScreen peut bloquer le lancement.
) else (
  echo Signature reussie.
)

:done
echo Termine.
exit /b 0
