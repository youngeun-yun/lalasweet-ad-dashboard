@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo  GitHub repo cleanup (keep same repo / URL)
echo  79MB -^> under 1MB, history reset
echo ============================================
echo.

REM ---- locate git ----
set "GIT="
where git >nul 2>&1 && set "GIT=git"
if not defined GIT if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT if exist "%ProgramFiles(x86)%\Git\cmd\git.exe" set "GIT=%ProgramFiles(x86)%\Git\cmd\git.exe"
if not defined GIT if exist "%LocalAppData%\Programs\Git\cmd\git.exe" set "GIT=%LocalAppData%\Programs\Git\cmd\git.exe"
if not defined GIT if exist "%UserProfile%\AppData\Local\Programs\Git\cmd\git.exe" set "GIT=%UserProfile%\AppData\Local\Programs\Git\cmd\git.exe"
if not defined GIT if exist "C:\Program Files\Git\bin\git.exe" set "GIT=C:\Program Files\Git\bin\git.exe"

REM ---- GitHub Desktop bundled git (app-x.y.z folder name changes per version) ----
if not defined GIT (
  for /f "delims=" %%D in ('dir /b /ad /o-n "%LocalAppData%\GitHubDesktop\app-*" 2^>nul') do (
    if not defined GIT if exist "%LocalAppData%\GitHubDesktop\%%D\resources\app\git\cmd\git.exe" (
      set "GIT=%LocalAppData%\GitHubDesktop\%%D\resources\app\git\cmd\git.exe"
    )
  )
)
if not defined GIT if exist "%LocalAppData%\GitHubDesktop\app\resources\app\git\cmd\git.exe" set "GIT=%LocalAppData%\GitHubDesktop\app\resources\app\git\cmd\git.exe"
if not defined GIT if exist "%ProgramFiles%\GitHub Desktop\resources\app\git\cmd\git.exe" set "GIT=%ProgramFiles%\GitHub Desktop\resources\app\git\cmd\git.exe"

if not defined GIT (
  echo [ERROR] git.exe not found.
  echo.
  echo  Tried: PATH / Git for Windows / GitHub Desktop bundled git
  echo.
  echo  Run the git-search bat file and send git_search.txt to Claude,
  echo  or install Git: https://git-scm.com/download/win
  echo.
  pause
  exit /b 1
)

echo  git found: %GIT%
"%GIT%" --version
echo.
echo  Repo  : youngeun-yun/lalasweet-ad-dashboard
echo  Branch: main (force replace)
echo.
echo  Streamlit app settings are NOT changed.
echo  The dashboard URL stays the same.
echo.
set /p OK=Type YES to continue:
if /i not "%OK%"=="YES" goto cancel

echo.
echo [1/5] git init...
if exist .git rmdir /s /q .git
"%GIT%" init -q
if errorlevel 1 goto err

echo [2/5] staging files...
"%GIT%" add .
if errorlevel 1 goto err

echo [3/5] commit...
"%GIT%" -c user.name="yunye" -c user.email="yunye@lalasweet.kr" commit -q -m "Repo cleanup: exclude data/, reset history (master data kept in Google Sheets)"
if errorlevel 1 goto err

echo [4/5] set remote and branch...
"%GIT%" branch -M main
"%GIT%" remote remove origin 2>nul
"%GIT%" remote add origin https://github.com/youngeun-yun/lalasweet-ad-dashboard.git
if errorlevel 1 goto err

echo [5/5] force push...
echo   (A browser or credential prompt may appear - sign in to GitHub)
"%GIT%" push -f origin main
if errorlevel 1 goto err

echo.
echo ============================================
echo  DONE!
echo.
echo  Next:
echo   1) Streamlit Cloud - Manage app - Reboot
echo   2) Dashboard should load fast now
echo ============================================
pause
exit /b 0

:err
echo.
echo [ERROR] Something failed. See the message above.
echo  - If auth failed: run this once, then retry:
echo      "%GIT%" config --global credential.helper manager
pause
exit /b 1

:cancel
echo Cancelled.
pause
exit /b 0
