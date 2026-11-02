@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo  Push updates (build_rd -^> Google Sheets)
echo ============================================
echo.

set "GIT="
where git >nul 2>&1 && set "GIT=git"
if not defined GIT if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT if exist "%LocalAppData%\Programs\Git\cmd\git.exe" set "GIT=%LocalAppData%\Programs\Git\cmd\git.exe"
if not defined GIT (
  for /f "delims=" %%D in ('dir /b /ad /o-n "%LocalAppData%\GitHubDesktop\app-*" 2^>nul') do (
    if not defined GIT if exist "%LocalAppData%\GitHubDesktop\%%D\resources\app\git\cmd\git.exe" (
      set "GIT=%LocalAppData%\GitHubDesktop\%%D\resources\app\git\cmd\git.exe"
    )
  )
)
if not defined GIT (
  echo [ERROR] git.exe not found.
  pause
  exit /b 1
)
echo  git: %GIT%
echo.

"%GIT%" add .
"%GIT%" -c user.name="yunye" -c user.email="yunye@lalasweet.kr" commit -q -m "build_rd: read/write master from Google Sheets + add safety guards"
if errorlevel 1 (
  echo  Nothing to commit, or commit failed.
)
"%GIT%" push origin main
if errorlevel 1 goto err

echo.
echo ============================================
echo  DONE! Pushed to main.
echo ============================================
pause
exit /b 0

:err
echo.
echo [ERROR] push failed. See message above.
pause
exit /b 1
