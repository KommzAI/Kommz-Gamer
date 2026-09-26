; ============================================================
; Kommz Gamer V5.2 — NSIS Installer Script
; ============================================================
; Usage:
;   1. Build Nuitka standalone first: run_standalone_build_community.bat
;   2. makensis.exe /DVERSION=5.2 /DEDITION=Community scripts\build_installer.nsi
; ============================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ── Defaults (override with /D on command line) ──────────────────
!ifndef VERSION
  !define VERSION "5.2"
!endif
!ifndef EDITION
  !define EDITION "Community"
!endif

; ── Metadata ─────────────────────────────────────────────────────
Name "Kommz Gamer ${EDITION} Edition"
OutFile "dist_standalone\Kommz_Gamer_V${VERSION}_${EDITION}_Setup.exe"

InstallDir "$PROGRAMFILES\Kommz Gamer"
InstallDirRegKey HKLM "Software\KommzGamer\${EDITION}" "InstallDir"

RequestExecutionLevel admin
SetCompressor /SOLID lzma

; ── Icon ─────────────────────────────────────────────────────────
!define MUI_ICON "..\icon.ico"
!define MUI_UNICON "..\icon.ico"

; ── Pages ────────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "French"

; ── Source directory (Nuitka standalone output) ──────────────────
!define SOURCE_DIR "..\dist_standalone\vtp_core.dist"

Section "Install"
  SetOutPath "$INSTDIR"

  ; Copy all files from the standalone build
  File /r "${SOURCE_DIR}\*.*"

  ; Create shortcuts
  CreateDirectory "$SMPROGRAMS\Kommz Gamer"
  CreateShortCut "$SMPROGRAMS\Kommz Gamer\Kommz Gamer ${EDITION}.lnk" "$INSTDIR\vtp_core.exe" "" "$INSTDIR\web\icon.ico"
  CreateShortCut "$SMPROGRAMS\Kommz Gamer\Désinstaller.lnk" "$INSTDIR\uninstall.exe"
  CreateShortCut "$DESKTOP\Kommz Gamer ${EDITION}.lnk" "$INSTDIR\vtp_core.exe" "" "$INSTDIR\web\icon.ico"

  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry for Add/Remove Programs
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "DisplayName" "Kommz Gamer ${EDITION} Edition"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "DisplayIcon" "$INSTDIR\web\icon.ico"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "Publisher" "Kommz Innovations"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "URLInfoAbout" "https://github.com/Kommz-Gamer/Kommz-Gamer"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "NoRepair" 1

  ; Store install dir for future updates
  WriteRegStr HKLM "Software\KommzGamer\${EDITION}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "Software\KommzGamer\${EDITION}" "Version" "${VERSION}"

  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  ; Remove shortcuts
  Delete "$SMPROGRAMS\Kommz Gamer\Kommz Gamer ${EDITION}.lnk"
  Delete "$SMPROGRAMS\Kommz Gamer\Désinstaller.lnk"
  RMDir "$SMPROGRAMS\Kommz Gamer"
  Delete "$DESKTOP\Kommz Gamer ${EDITION}.lnk"

  ; Remove installed files
  RMDir /r "$INSTDIR"

  ; Remove registry entries
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\KommzGamer_${EDITION}"
  DeleteRegKey HKLM "Software\KommzGamer\${EDITION}"
SectionEnd
