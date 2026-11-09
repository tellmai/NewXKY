@echo off
rem ASCII only: cmd.exe parses batch files with the console code page, so any
rem non-ASCII text here can break the parser. User-facing Chinese guidance
rem lives in README.md, in the packaged readme and in the app's own dialog.
setlocal
cd /d "%~dp0"
echo ==========================================
echo    NewXKY runtime check
echo ==========================================
echo.
ver
set "BUILD="
for /f "tokens=4,5,6 delims=. " %%A in ('ver') do set "BUILD=%%C"
set "TOOOLD="
for /f "delims=0123456789" %%X in ("%BUILD%") do set "BUILD=0"
if not defined BUILD set "BUILD=0"
if "%BUILD%"=="" set "BUILD=0"
if %BUILD% LSS 17763 (
  echo   [WARN] Windows build %BUILD% is older than 1809 ^(17763^).
  set "TOOOLD=1"
) else (
  echo   [ ok ] Windows build %BUILD% ^(1809 or newer^)
)
echo.
set "MISSING="
for %%F in (
  "NewXKY.exe"
  "_internal\python311.dll"
  "_internal\PySide6\Qt6Core.dll"
  "_internal\PySide6\plugins\platforms\qwindows.dll"
  "_internal\VCRUNTIME140.dll"
  "_internal\VCRUNTIME140_1.dll"
  "_internal\MSVCP140.dll"
  "_internal\ucrtbase.dll"
  "_internal\api-ms-win-core-sysinfo-l1-2-0.dll"
  "_internal\api-ms-win-crt-runtime-l1-1-0.dll"
) do (
  if exist "%%~F" (echo   [ ok ] %%~F) else (echo   [MISS] %%~F & set "MISSING=1")
)
if exist "_internal\question-bank\default-bank.json" (
  echo   [ ok ] _internal\question-bank\default-bank.json
) else (
  set "BANK="
  for /d %%D in ("*") do if exist "%%~D\default-bank.json" set "BANK=1"
  if not defined BANK for /d %%D in ("_internal\*") do if exist "%%~D\default-bank.json" set "BANK=1"
  if defined BANK (echo   [ ok ] question bank found) else (
    echo   [MISS] question bank: default-bank.json & set "MISSING=1"
  )
)
echo.
if defined TOOOLD (
  echo RESULT: UNSUPPORTED OS - this app needs Windows 10 1809 x64 or newer.
  echo         On older systems Python and Qt cannot start at all.
)
if defined MISSING (
  echo RESULT: INCOMPLETE - extract the whole ZIP again and keep _internal/
  echo         Do not copy NewXKY.exe alone. Do not run it from inside the ZIP
  echo         or from a OneDrive-synced folder.
) else if not defined TOOOLD (
  echo RESULT: FILES OK - if it still fails, install
  echo         "Microsoft Visual C++ 2015-2022 Redistributable (x64)".
)
echo.
echo Requires Windows 10 1809 x64 or newer. See README.md for details.
echo.
pause
