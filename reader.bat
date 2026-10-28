@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py"
    exit /b 0
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0app.py"
    exit /b 0
)
where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%~dp0app.py"
    exit /b 0
)
echo Python'un pythonw.exe calistiricisi bulunamadi. Python kurulumunu kontrol edin.
pause
