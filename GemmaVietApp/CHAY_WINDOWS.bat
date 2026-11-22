@echo off
setlocal
cd /d "%~dp0"
title Gemma Viet - AI chay tren may
set "PYTHONUTF8=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

echo ============================================================
echo   GEMMA VIET - AI chay tren may cua ban
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" goto install

echo [1/3] Tim Python tren may...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

echo [2/3] Tao moi truong rieng (.venv)...
%PY% -m venv .venv
if errorlevel 1 goto nopython

:install
set "VPY=.venv\Scripts\python.exe"
if exist ".venv\.da_cai_xong" goto run

echo [3/3] Cai thu vien. Lan dau mat 5-15 phut (tai khoang 3 GB)...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto failed
"%VPY%" setup_torch.py
if errorlevel 1 goto failed
echo ok> ".venv\.da_cai_xong"
echo.
echo Cai dat xong!
echo.

:run
echo Dang khoi dong... (lan dau se tai model khoang 540 MB)
echo.
"%VPY%" app.py %*
echo.
pause
exit /b 0

:nopython
echo.
echo [LOI] Khong tim thay Python (can Python 3.10 tro len).
echo   1. Tai Python tai: https://www.python.org/downloads/
echo   2. Khi cai, nho tick o "Add python.exe to PATH"
echo   3. Chay lai file CHAY_WINDOWS.bat nay
echo.
pause
exit /b 1

:failed
echo.
echo [LOI] Cai thu vien that bai. Kiem tra mang Internet roi chay lai file nay.
echo       Neu van loi, xoa thu muc .venv roi chay lai.
echo.
pause
exit /b 1
