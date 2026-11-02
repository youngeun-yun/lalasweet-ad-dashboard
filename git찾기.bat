@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "OUT=%~dp0git_search.txt"
echo ==== git search ==== > "%OUT%"
echo. >> "%OUT%"

echo Searching for git.exe on this PC...
echo (this may take 1-2 minutes)
echo.

echo [where git] >> "%OUT%"
where git >> "%OUT%" 2>&1
echo. >> "%OUT%"

echo [common paths] >> "%OUT%"
for %%P in (
 "%ProgramFiles%\Git\cmd\git.exe"
 "%ProgramFiles%\Git\bin\git.exe"
 "%ProgramFiles(x86)%\Git\cmd\git.exe"
 "%LocalAppData%\Programs\Git\cmd\git.exe"
 "%LocalAppData%\GitHubDesktop\app-*\resources\app\git\cmd\git.exe"
 "%ProgramFiles%\GitHub Desktop\resources\app\git\cmd\git.exe"
) do (
  if exist "%%~P" (echo FOUND %%~P >> "%OUT%") else (echo no    %%~P >> "%OUT%")
)
echo. >> "%OUT%"

echo [GitHub Desktop folder] >> "%OUT%"
if exist "%LocalAppData%\GitHubDesktop" (
  dir /b "%LocalAppData%\GitHubDesktop" >> "%OUT%" 2>&1
) else (
  echo GitHub Desktop not installed >> "%OUT%"
)
echo. >> "%OUT%"

echo [full scan C: for git.exe] >> "%OUT%"
dir /s /b C:\git.exe >> "%OUT%" 2>nul
dir /s /b "C:\Program Files\git.exe" >> "%OUT%" 2>nul
for /f "delims=" %%F in ('dir /s /b "C:\Users\%USERNAME%\git.exe" 2^>nul') do echo %%F >> "%OUT%"
where /r "C:\Program Files" git.exe >> "%OUT%" 2>nul
where /r "C:\Users\%USERNAME%\AppData" git.exe >> "%OUT%" 2>nul
echo. >> "%OUT%"
echo ==== end ==== >> "%OUT%"

echo.
echo Done. Result saved to: git_search.txt
echo Please send that file to Claude.
echo.
pause
