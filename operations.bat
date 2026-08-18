@echo off
setlocal enabledelayedexpansion
title min-implant-v2 Operation and maintenance menu

rem ============================================================
rem  Portable path detection: Prioritize environment variables, Secondly PATH, last common location
rem  PYTHON  -> backend runtime (Optional, but necessary)
rem  NODE    -> sentinel mint / Front-end build (required)
rem ============================================================
rem Prefer the bundled Python runtime when available; otherwise use Python from PATH.
if not defined PYTHON if exist "%TEMP%\opencode\pyfull\python.exe" set "PYTHON=%TEMP%\opencode\pyfull\python.exe"
if defined PYTHON (set "PY=%PYTHON%") else (set "PY=python")
if defined NODE_BIN (set "NODE=%NODE_BIN%") else (set "NODE=node")

set "WORKDIR=%~dp0backend"
set "FEWORK=%~dp0frontend"
set "PORT=8770"
set "FEPORT=5173"
set "LOGDIR=%TEMP%\min-implant-v2"

rem ==== 711 residential proxy creds: env first, then local file (never in git) ====
if not defined PROXY_711_USER if exist "%USERPROFILE%\.min_711_creds.bat" call "%USERPROFILE%\.min_711_creds.bat"

rem ==== api798 Register card secret file（Can be overridden by environment variables）====
if not defined REG_API798_MAILBOXES (
  if exist "%TEMP%\opencode\mailboxes_20260816.txt" set "REG_API798_MAILBOXES=%TEMP%\opencode\mailboxes_20260816.txt"
)
set "OUT=%LOGDIR%\backend_out.log"
set "ERR=%LOGDIR%\backend_err.log"
set "FEOUT=%LOGDIR%\frontend_out.log"
set "FEERR=%LOGDIR%\frontend_err.log"
set "VITE=%~dp0frontend\node_modules\vite\bin\vite.js"

rem Make sure the log directory exists (Start-Process -Redirect* need)
powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path '%LOGDIR%' | Out-Null"

:menu
cls
echo ============================================
echo        min-implant-v2 Operation and maintenance menu
echo ============================================
echo   [rear end]
echo    1. environmental inspection(port/healthy/acting/log/front-end port)
echo    2. One-click restart(rear end + Front-end build)
echo    3. One-click restart(rear end + front enddev)
echo    4. Start backend
echo    5. Stop backend
echo    6. Backend log tail 20 OK
echo    7. Error log tail 20 OK
echo    8. Real-time backend logs(Ctrl+C quit)
echo   [front end]
echo    9.  front end dev start up(vite %FEPORT%)
echo   10.  front end dev Restart
echo   11.  front end dev stop
echo   12.  Front-end build(vite build -^> web/dist)
echo   13.  Front end log tail 20 OK
echo   [maintain]
echo   14.  clean up __pycache__ Table of contents
echo   15.  quit
echo ============================================

set "valid= 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 "
:ask
set "ch="
set /p "ch=Please select [1-15]: " <con
if not defined ch goto ask
if "!valid: %ch% =!"=="!valid!" goto ask

if "%ch%"=="1" goto check
if "%ch%"=="2" goto restart
if "%ch%"=="3" goto restart_all
if "%ch%"=="4" goto start
if "%ch%"=="5" goto stop
if "%ch%"=="6" goto log_out
if "%ch%"=="7" goto log_err
if "%ch%"=="8" goto tail
if "%ch%"=="9" goto fe_start
if "%ch%"=="10" goto fe_restart
if "%ch%"=="11" goto fe_stop
if "%ch%"=="12" goto fe_build
if "%ch%"=="13" goto fe_log
if "%ch%"=="14" goto pycache
if "%ch%"=="15" exit
goto menu

:check
echo.
echo ---------- 1/6 backend port %PORT% ----------
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -EA SilentlyContinue; if($c){'%PORT% LISTEN, PID='+$c.OwningProcess}else{'%PORT% Not listening(Backend not started)'}"
echo.
echo ---------- 2/6 Backend health ----------
powershell -NoProfile -Command "try{$h=Invoke-RestMethod 'http://127.0.0.1:%PORT%/api/health' -UseBasicParsing -TimeoutSec 8;'health OK, mode='+$h.chain_mode}catch{'health FAIL: '+$_.Exception.Message}"
echo.
echo ---------- 3/6 proxy relay port (Clash 7890 / relay 18794) ----------
powershell -NoProfile -Command "7890,18794 | %%{ $r=Test-NetConnection 127.0.0.1 -Port $_ -WarningAction SilentlyContinue; 'port '+$_+': '+$(if($r.TcpTestSucceeded){'OPEN'}else{'CLOSED'}) }"
echo.
echo ---------- 4/6 front end dev port %FEPORT% ----------
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %FEPORT% -State Listen -EA SilentlyContinue; if($c){'%FEPORT% LISTEN, PID='+$c.OwningProcess}else{'%FEPORT% Not listening(front end dev Not started)'}"
echo.
echo ---------- 5/6 Backend log tail ----------
powershell -NoProfile -Command "if(Test-Path '%OUT%'){Get-Content '%OUT%' -Tail 5 -Encoding UTF8}else{'Log file does not exist(Not started)'}"
echo.
echo ---------- 6/6 disk space ----------
powershell -NoProfile -Command "Get-PSDrive C | %%{ 'Cdisk available '+[math]::Round($_.Free/1GB,1)+' GB / common '+[math]::Round(($_.Free+$_.Used)/1GB,1)+' GB' }"
echo.
goto back

:restart
echo.
echo [1/4] Stop backend...
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -EA SilentlyContinue; if($c){Stop-Process -Id $c.OwningProcess -Force; 'Stopped PID='+$c.OwningProcess}else{'Backend is not running'}"
echo [2/4] Start backend...
powershell -NoProfile -Command "$p = Start-Process -FilePath '%PY%' -ArgumentList '-m','uvicorn','app:app','--host','127.0.0.1','--port','%PORT%' -WorkingDirectory '%~dp0backend' -RedirectStandardOutput '%OUT%' -RedirectStandardError '%ERR%' -WindowStyle Hidden -PassThru; Start-Sleep 6; $c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -EA SilentlyContinue; if($c){'Backend started PID='+$c.OwningProcess}else{'Backend startup failed, Please check the log (Options 7)'}"
echo [3/4] Build the frontend...
if not exist "%VITE%" (
  echo [!] not found vite: %VITE%
  echo [!] please first frontend directory execution: npm install
) else (
  cd /d "%FEWORK%"
  "%NODE%" "%VITE%" build
  set "BUILD_ERR=!errorlevel!"
  cd /d "%WORKDIR%"
  if not "!BUILD_ERR!"=="0" echo [!!] Frontend build failed, exit code !BUILD_ERR!
  if "!BUILD_ERR!"=="0" echo Front-end build completed
)
echo.
echo [4/4] Finish
goto back

:restart_all
echo.
echo [1/5] Stop backend...
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -EA SilentlyContinue; if($c){Stop-Process -Id $c.OwningProcess -Force; 'Stopped PID='+$c.OwningProcess}else{'Backend is not running'}"
echo [2/5] Stop the frontend dev...
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %FEPORT% -State Listen -EA SilentlyContinue; if($c){Stop-Process -Id $c.OwningProcess -Force; 'Stopped PID='+$c.OwningProcess}else{'front end dev Not running'}"
echo [3/5] Start backend...
powershell -NoProfile -Command "$p = Start-Process -FilePath '%PY%' -ArgumentList '-m','uvicorn','app:app','--host','127.0.0.1','--port','%PORT%' -WorkingDirectory '%~dp0backend' -RedirectStandardOutput '%OUT%' -RedirectStandardError '%ERR%' -WindowStyle Hidden -PassThru; Start-Sleep 6; $c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -EA SilentlyContinue; if($c){'Backend started PID='+$c.OwningProcess}else{'Backend startup failed, Please check the log (Options 7)'}"
echo [4/5] Start the frontend dev...
if not exist "%VITE%" (
  echo [!] not found vite: %VITE%
  echo [!] please first frontend directory execution: npm install
) else (
  powershell -NoProfile -Command "Start-Process -FilePath '%NODE%' -ArgumentList '%VITE%','--port','%FEPORT%','--host','127.0.0.1' -WorkingDirectory '%FEWORK%' -RedirectStandardOutput '%FEOUT%' -RedirectStandardError '%FEERR%' -WindowStyle Hidden; Start-Sleep 5; $c2=Get-NetTCPConnection -LocalPort %FEPORT% -State Listen -EA SilentlyContinue; if($c2){'front end dev Started PID='+$c2.OwningProcess}else{'front end dev Startup failed, Please check the log (Options 13)'}"
)
echo [5/5] Finish
goto back

:start
echo.
echo Start backend...
powershell -NoProfile -Command "$p = Start-Process -FilePath '%PY%' -ArgumentList '-m','uvicorn','app:app','--host','127.0.0.1','--port','%PORT%' -WorkingDirectory '%~dp0backend' -RedirectStandardOutput '%OUT%' -RedirectStandardError '%ERR%' -WindowStyle Hidden -PassThru; Start-Sleep 6; $c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -EA SilentlyContinue; if($c){'Backend started PID='+$c.OwningProcess}else{'Backend startup failed, Please check the log (Options 7)'}"
goto back

:stop
echo.
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -EA SilentlyContinue; if($c){Stop-Process -Id $c.OwningProcess -Force; 'Stopped PID='+$c.OwningProcess}else{'Backend is not running'}"
goto back

:log_out
echo.
powershell -NoProfile -Command "Get-Content '%OUT%' -Tail 20 -Encoding UTF8"
echo.
goto back

:log_err
echo.
powershell -NoProfile -Command "if(Test-Path '%ERR%'){Get-Content '%ERR%' -Tail 20 -Encoding UTF8}else{'Error log does not exist'}"
echo.
goto back

:tail
echo.
echo Real-time backend logs(according to Ctrl+C quit)...
powershell -NoProfile -Command "Get-Content '%OUT%' -Tail 20 -Wait -Encoding UTF8"
echo.
goto back

:fe_start
echo.
echo Start the frontend dev server (%FEPORT%)...
if not exist "%VITE%" (
  echo [!] not found vite: %VITE%
  echo [!] please first frontend directory execution: npm install
) else (
  powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %FEPORT% -State Listen -EA SilentlyContinue; if($c){'front end dev Already running PID='+$c.OwningProcess}else{Start-Process -FilePath '%NODE%' -ArgumentList '%VITE%','--port','%FEPORT%','--host','127.0.0.1' -WorkingDirectory '%FEWORK%' -RedirectStandardOutput '%FEOUT%' -RedirectStandardError '%FEERR%' -WindowStyle Hidden; Start-Sleep 5; $c2=Get-NetTCPConnection -LocalPort %FEPORT% -State Listen -EA SilentlyContinue; if($c2){'front end dev Started PID='+$c2.OwningProcess}else{'front end dev Startup failed, Please check the log (Options 13)'}}"
)
goto back

:fe_restart
echo.
echo Restart the front end dev server...
if not exist "%VITE%" (
  echo [!] not found vite: %VITE%
  echo [!] please first frontend directory execution: npm install
) else (
  powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %FEPORT% -State Listen -EA SilentlyContinue; if($c){Stop-Process -Id $c.OwningProcess -Force; 'Stopped PID='+$c.OwningProcess}; Start-Sleep 2; Start-Process -FilePath '%NODE%' -ArgumentList '%VITE%','--port','%FEPORT%','--host','127.0.0.1' -WorkingDirectory '%FEWORK%' -RedirectStandardOutput '%FEOUT%' -RedirectStandardError '%FEERR%' -WindowStyle Hidden; Start-Sleep 5; $c2=Get-NetTCPConnection -LocalPort %FEPORT% -State Listen -EA SilentlyContinue; if($c2){'front end dev Started PID='+$c2.OwningProcess}else{'front end dev Startup failed, Please check the log (Options 13)'}"
)
goto back

:fe_stop
echo.
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort %FEPORT% -State Listen -EA SilentlyContinue; if($c){Stop-Process -Id $c.OwningProcess -Force; 'Stopped PID='+$c.OwningProcess}else{'front end dev Not running'}"
goto back

:fe_build
echo.
echo Front-end build(vite build -^> web/dist)...
if not exist "%VITE%" (
  echo [!] not found vite: %VITE%
  echo [!] please first frontend directory execution: npm install
) else (
  cd /d "%FEWORK%"
  "%NODE%" "%VITE%" build
  set "BUILD_ERR=!errorlevel!"
  cd /d "%WORKDIR%"
  if not "!BUILD_ERR!"=="0" echo [!!] Frontend build failed, exit code !BUILD_ERR!
  if "!BUILD_ERR!"=="0" echo Front-end build completed
)
echo.
goto back

:fe_log
echo.
powershell -NoProfile -Command "if(Test-Path '%FEOUT%'){Get-Content '%FEOUT%' -Tail 20 -Encoding UTF8}else{'The front-end log does not exist'}"
echo.
goto back

:pycache
echo.
powershell -NoProfile -Command "Get-ChildItem '%~dp0backend' -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force; 'pycache Cleaned'"
goto back

:back
echo.
echo ============================================
echo  Press Enter to return to the main menu...
pause <con >nul
goto menu
