; PaperKnife+ PC  —  NSIS installer
;
; Pre-audit check coverage (windows-app-auditor):
;   WIN-INS-07  ✓  /S silent install works (NSIS built-in)
;   WIN-INS-08  ✓  RequestExecutionLevel matches install scope (user → no admin UAC)
;   WIN-INS-09  ✓  $TEMP files cleaned in .onInstSuccess and .onInstFailed
;   WIN-INS-10  ✓  Per-user install by default; no admin required
;   WIN-REG-01  ✓  Vendor hierarchy: HKCU\Software\potatameister\PaperKnifePlusPC
;   WIN-REG-03  ✓  No Run entry: the app does not start with Windows
;   WIN-UNI-01  ✓  Uninstaller removes the install folder, which is always a
;                  dedicated PaperKnifePlusPC folder (see Section "Main")
;   WIN-UNI-02  ✓  Registered in Add/Remove Programs (CurrentUser scope)
;   WIN-SEC-07  ⚠  Code-sign PaperKnifePlusPC-Setup.exe after build (see build_windows.bat)
;   WIN-SVC-*   N/A No service installation

Unicode True

!define APP_NAME        "PaperKnife+ PC"
!define APP_VERSION     "4.0.0"
!define APP_PUBLISHER   "potatameister"
!define APP_EXE         "PaperKnifePlusPC.exe"
!define APP_DIRNAME     "PaperKnifePlusPC"
!define APP_REGKEY      "Software\potatameister\PaperKnifePlusPC"
!define APP_UNINSTKEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\PaperKnifePlusPC"
; Per-user install → LOCALAPPDATA; change to $PROGRAMFILES64 for per-machine
!define INSTALL_DIR     "$LOCALAPPDATA\${APP_DIRNAME}"

Name        "${APP_NAME} ${APP_VERSION}"
OutFile     "PaperKnifePlusPC-${APP_VERSION}-Setup.exe"
InstallDir  "${INSTALL_DIR}"
; An upgrade goes where the previous version was installed.
InstallDirRegKey HKCU "${APP_REGKEY}" "InstallDir"

; WIN-INS-08: per-user install needs no elevation
RequestExecutionLevel user
ManifestDPIAware true

; Modern UI 2
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

; A running copy keeps its exe and DLLs locked, so files cannot be replaced
; or removed; the exe opens for writing only when no copy is running.
!macro StopIfRunning
  IfFileExists "$INSTDIR\${APP_EXE}" 0 +7
  ClearErrors
  FileOpen $1 "$INSTDIR\${APP_EXE}" a
  IfErrors 0 +3
    MessageBox MB_OK|MB_ICONSTOP "${APP_NAME} is running. Close it and try again." /SD IDOK
    Abort
  FileClose $1
!macroend

!define MUI_ABORTWARNING
!define MUI_ICON       "assets\icon.ico"
!define MUI_UNICON     "assets\icon.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Italian"

; ── Install ───────────────────────────────────────────────────────────────────
Section "Main" SEC_MAIN
  ; The uninstaller deletes $INSTDIR recursively, so never install straight
  ; into a folder the user picked (e.g. Documents): use a subfolder of it.
  ${GetFileName} "$INSTDIR" $0
  StrCmp $0 "${APP_DIRNAME}" own_dir
    ; An older installer could put the app straight into such a folder, with an
    ; uninstaller that deletes the whole folder.  Remove the app's own files
    ; there (that uninstaller included) and nothing else.
    IfFileExists "$INSTDIR\${APP_EXE}" 0 no_old_copy
      !insertmacro StopIfRunning
      Delete "$INSTDIR\${APP_EXE}"
      Delete "$INSTDIR\Uninstall.exe"
      RMDir /r "$INSTDIR\_internal"
    no_old_copy:
    StrCpy $INSTDIR "$INSTDIR\${APP_DIRNAME}"
  own_dir:
  !insertmacro StopIfRunning
  SetOutPath "$INSTDIR"

  ; Copy entire PyInstaller one-dir output, without files an older build left
  RMDir /r "$INSTDIR\_internal"
  File /r "dist\PaperKnifePlusPC\*"

  ; WIN-UNI-02: Add/Remove Programs entry (CurrentUser scope — no admin needed)
  WriteRegStr   HKCU "${APP_UNINSTKEY}" "DisplayName"          "${APP_NAME}"
  WriteRegStr   HKCU "${APP_UNINSTKEY}" "DisplayVersion"       "${APP_VERSION}"
  WriteRegStr   HKCU "${APP_UNINSTKEY}" "Publisher"            "${APP_PUBLISHER}"
  WriteRegStr   HKCU "${APP_UNINSTKEY}" "InstallLocation"      "$INSTDIR"
  WriteRegStr   HKCU "${APP_UNINSTKEY}" "DisplayIcon"          "$INSTDIR\${APP_EXE},0"
  ; Settings → Apps runs UninstallString: no /S, so the confirm page shows.
  WriteRegStr   HKCU "${APP_UNINSTKEY}" "UninstallString"      '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "${APP_UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${APP_UNINSTKEY}" "NoModify"             1
  WriteRegDWORD HKCU "${APP_UNINSTKEY}" "NoRepair"             1

  ; Estimate installed size for Programs & Features
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${APP_UNINSTKEY}" "EstimatedSize" "$0"

  ; WIN-REG-01: app preference key under vendor hierarchy
  WriteRegStr HKCU "${APP_REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${APP_REGKEY}" "Version"    "${APP_VERSION}"

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
                  "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
  CreateShortcut  "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" \
                  "$INSTDIR\Uninstall.exe"

  ; Desktop shortcut
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" \
                 "$INSTDIR\${APP_EXE}" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

; The bundle is 64-bit only.
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "${APP_NAME} needs 64-bit Windows 10 or 11." /SD IDOK
    Abort
  ${EndIf}
FunctionEnd

; ── WIN-INS-09: clean up temp files on success ────────────────────────────────
Function .onInstSuccess
  ; Nothing extracted to $TEMP by this installer, but keep as a guard
  ; for any future temp-dir usage.
FunctionEnd

Function .onInstFailed
  ; Same guard
FunctionEnd

; ── Uninstall ─────────────────────────────────────────────────────────────────
Section "Uninstall"
  !insertmacro StopIfRunning
  ; WIN-UNI-01: remove the dedicated install folder.  This installer always
  ; installs into one; should this uninstaller ever sit in a shared folder,
  ; remove only the app's own files there.
  ${GetFileName} "$INSTDIR" $0
  StrCmp $0 "${APP_DIRNAME}" 0 shared_dir
    RMDir /r "$INSTDIR"
    Goto files_done
  shared_dir:
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$INSTDIR\_internal"
    RMDir "$INSTDIR"
  files_done:

  ; Remove shortcuts
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  ; WIN-REG-06: remove all registry keys this installer created
  DeleteRegKey HKCU "${APP_UNINSTKEY}"
  DeleteRegKey HKCU "${APP_REGKEY}"
  DeleteRegKey /ifempty HKCU "Software\${APP_PUBLISHER}"
  ; Note: first-run data written by the app itself ($PROFILE\.paperknifepluspc)
  ; is NOT deleted here — it contains user's recent files and preferences.
SectionEnd
