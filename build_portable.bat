@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PYTHON=.venv310qt5\Scripts\python.exe"
set "APP_EXE=dist\MyPhotoStudio\MyPhotoStudio.exe"

if not exist "%PYTHON%" goto missing
"%PYTHON%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 goto missing_build

echo [1/3] Sinh icon ung dung...
"%PYTHON%" tools\make_app_icon.py
if errorlevel 1 goto failed

echo [2/3] Dong goi bang PyInstaller...
"%PYTHON%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller MyPhotoStudio.spec
if errorlevel 1 goto failed

echo [3/3] Nen goi portable...
"%PYTHON%" -c "from config.settings import APP_VERSION; print(APP_VERSION)" > "%TEMP%\myphoto_appver.txt"
set /p APPVER=<"%TEMP%\myphoto_appver.txt"
del "%TEMP%\myphoto_appver.txt" >nul 2>&1
if not defined APPVER set "APPVER=dev"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\MyPhotoStudio\*' -DestinationPath ('dist\MyPhotoStudio-portable-%APPVER%.zip') -Force"
if errorlevel 1 goto failed

echo.
echo Xong: %APP_EXE%
echo Zip:  dist\MyPhotoStudio-portable-%APPVER%.zip
exit /b 0

:missing
echo Khong tim thay .venv310qt5\Scripts\python.exe.
echo Xem README.md muc "Cai dat lan dau".
exit /b 1

:missing_build
echo Chua cai PyInstaller trong .venv310qt5. Chay:
echo   uv pip install --python .venv310qt5\Scripts\python.exe -r requirements-build.txt
exit /b 1

:failed
echo Dong goi that bai. Xem log o tren.
exit /b 1
