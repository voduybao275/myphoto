@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv310qt5\Scripts\python.exe" goto missing
".venv310qt5\Scripts\python.exe" main.py %*
exit /b %errorlevel%

:missing
echo Khong tim thay moi truong .venv310qt5.
echo Xem README.md, muc "Cai dat lan dau".
pause
exit /b 1
