@echo off
setlocal
cd /d "%~dp0"
title AI Viet Studio
set "PYTHONUTF8=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

echo ============================================================
echo   AI VIET STUDIO - AI chay ngay tren may cua ban
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" goto deps

echo [1/4] Tim Python tren may...
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython

echo [2/4] Tao moi truong rieng (.venv)...
%PY% -m venv .venv
if errorlevel 1 goto nopython

:deps
set "VPY=.venv\Scripts\python.exe"
if exist ".venv\.deps_ok" goto torch
echo [3/4] Cai thu vien co ban...
"%VPY%" -m pip install --upgrade pip
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo ok> ".venv\.deps_ok"

:torch
if exist ".venv\.torch_ok" goto ollama
echo [4/4] Cai PyTorch cho tab "So sanh Gemma" - khoang 3 GB, chi lam 1 lan...
"%VPY%" setup_torch.py
if errorlevel 1 goto torch_failed
echo ok> ".venv\.torch_ok"
goto ollama

:torch_failed
echo.
echo [CANH BAO] Chua cai duoc PyTorch. Tab "So sanh Gemma" tam thoi chua dung duoc.
echo            Cac tab khac van dung binh thuong. Lan sau chay lai se thu cai tiep.
echo.

:ollama
set "HAS_OLLAMA="
where ollama >nul 2>nul && set "HAS_OLLAMA=1"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "HAS_OLLAMA=1"
if defined HAS_OLLAMA goto run
if exist ".venv\.skip_ollama" goto run

echo.
echo ------------------------------------------------------------
echo  Chua thay Ollama tren may.
echo  Ollama la phan mem mien phi giup chay cac model AI lon
echo  - nhu Qwen3, Llama - tren card do hoa de tro chuyen.
echo ------------------------------------------------------------
choice /C YN /M "Ban co muon cai Ollama ngay bay gio"
if errorlevel 2 goto skip_ollama

where winget >nul 2>nul
if errorlevel 1 goto ollama_manual
echo Dang cai Ollama bang winget...
winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 goto ollama_manual
echo Da cai Ollama. Dang mo Ollama...
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
goto run

:ollama_manual
echo Khong cai tu dong duoc. Dang mo trang tai Ollama - hay tai va cai dat nhu phan mem thuong.
start "" "https://ollama.com/download"
goto run

:skip_ollama
echo ok> ".venv\.skip_ollama"
echo Bo qua. Ban co the cai Ollama sau, xem huong dan o tab "Mo hinh" trong ung dung.

:run
echo.
echo Dang khoi dong AI Viet Studio...
echo.
"%VPY%" app.py %*
echo.
pause
exit /b 0

:nopython
echo.
echo [LOI] Khong tim thay Python - can Python 3.10 tro len.
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
