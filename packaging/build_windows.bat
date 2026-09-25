@echo off
rem Pixel Buddy - Windows build. Double-click this file.
rem Installs Python if needed, builds "Pixel Buddy.exe", adds Desktop + Start Menu shortcuts, starts him.
setlocal
cd /d "%~dp0\.."
echo === Building Pixel Buddy for Windows ===

where py >nul 2>nul
if errorlevel 1 (
    echo Python isn't installed. Installing Python 3.12 with winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo Couldn't install Python automatically. Get it from https://www.python.org/downloads/
        echo then double-click build_windows.bat again.
        pause
        exit /b 1
    )
    echo Python installed. Close this window and double-click build_windows.bat again.
    pause
    exit /b 0
)

if not exist .venv (
    py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller || goto :fail
python packaging\make_icons.py || goto :fail
pyinstaller packaging\pixel_buddy.spec --noconfirm --distpath dist --workpath build\pyinstaller || goto :fail

echo Adding Desktop and Start Menu shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$exe = (Resolve-Path 'dist\Pixel Buddy\Pixel Buddy.exe').Path;" ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  $s = $ws.CreateShortcut((Join-Path $dir 'Pixel Buddy.lnk'));" ^
  "  $s.TargetPath = $exe; $s.WorkingDirectory = (Split-Path $exe); $s.IconLocation = $exe; $s.Save() }"

echo.
echo Done! Starting Pixel Buddy. Look for the crab in the system tray (by the clock).
start "" "dist\Pixel Buddy\Pixel Buddy.exe"
exit /b 0

:fail
echo.
echo Build failed. Scroll up for the error.
pause
exit /b 1
