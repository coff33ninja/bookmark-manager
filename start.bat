@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "VENV_PATH=%SCRIPT_DIR%.venv"
set "VENV_ACTIVATE_SCRIPT=%VENV_PATH%\Scripts\activate.bat"
set "REQUIREMENTS_FILE=%SCRIPT_DIR%requirements.txt"

echo Navigating to project directory: %~dp0
cd /d "%SCRIPT_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to change directory to %SCRIPT_DIR%.
    pause
    exit /b 1
)

echo Activating virtual environment using %VENV_ACTIVATE_SCRIPT%...
if not exist "%VENV_ACTIVATE_SCRIPT%" (
    echo ERROR: Virtual environment activation script not found at %VENV_ACTIVATE_SCRIPT%.
    echo Please ensure the virtual environment '.venv' has been created in %SCRIPT_DIR%.
    pause
    exit /b 1
)
call "%VENV_ACTIVATE_SCRIPT%"
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)

echo Installing dependencies from %REQUIREMENTS_FILE%...
if not exist "%REQUIREMENTS_FILE%" (
    echo ERROR: %REQUIREMENTS_FILE% not found. Cannot install dependencies.
    pause
    exit /b 1
)
python -m pip install -r "%REQUIREMENTS_FILE%" --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies from %REQUIREMENTS_FILE%.
    pause
    exit /b 1
)

set "UVICORN_HOST=127.0.0.1"
set "UVICORN_PORT=8000"
set "WEBSITE_PATH=/website"
set "FULL_WEBSITE_URL=http://%UVICORN_HOST%:%UVICORN_PORT%%WEBSITE_PATH%"

echo Starting FastAPI application in a new window...
echo You will be able to access the application at: %FULL_WEBSITE_URL%
echo The server will run in a new, separate window.
echo Press Ctrl+C in that new window to stop the server.

START "FastAPI Server" cmd /k "echo Activating venv for server window... && call ""%VENV_ACTIVATE_SCRIPT%"" && echo Starting Uvicorn on %UVICORN_HOST%:%UVICORN_PORT%... && python -m uvicorn app.main:app --host %UVICORN_HOST% --port %UVICORN_PORT% --reload"

echo.
echo Waiting for the FastAPI application to become available at %FULL_WEBSITE_URL% ...
echo This might take a few moments. Please be patient.

echo DEBUG: Initializing loop variables.
set "MAX_ATTEMPTS=60"
set "ATTEMPT_NUM=0"
echo DEBUG: MAX_ATTEMPTS=%MAX_ATTEMPTS%, ATTEMPT_NUM=%ATTEMPT_NUM%

:waitForServerLoop
echo DEBUG: Entered :waitForServerLoop
set /a ATTEMPT_NUM+=1
echo DEBUG: ATTEMPT_NUM incremented to %ATTEMPT_NUM%

echo DEBUG: Checking condition: IF %ATTEMPT_NUM% GTR %MAX_ATTEMPTS%
if %ATTEMPT_NUM% GTR %MAX_ATTEMPTS% goto :serverTimeout
echo DEBUG: Condition FALSE (continuing loop, will attempt PowerShell check)

echo Attempt %ATTEMPT_NUM% of %MAX_ATTEMPTS%: Checking server status at %FULL_WEBSITE_URL% ...

powershell -Command "try { $response = Invoke-WebRequest -Uri '%FULL_WEBSITE_URL%' -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop; if ($response.StatusCode -eq 200) { exit 0 } else { Write-Host ('Received status: ' + $response.StatusCode); exit 1 } } catch { Write-Host ('Connection failed: ' + $_.Exception.Message); exit 1 }"
echo DEBUG: PowerShell exit code (errorlevel): %errorlevel%
if %errorlevel% EQU 0 (
    echo DEBUG: Server is up! (errorlevel 0)
    echo Server is up and running!
    goto :launchBrowser
) else (
    echo DEBUG: Server not yet up or PowerShell check failed (errorlevel %errorlevel%).
)

timeout /t 1 /nobreak >nul
goto :waitForServerLoop

:launchBrowser
echo.
echo Launching website in your default browser: %FULL_WEBSITE_URL%
start "" "%FULL_WEBSITE_URL%"

echo.
echo The FastAPI server is running in the "FastAPI Server" window.
echo You can close this script window (the one you are reading this message in).
echo To stop the server, close the "FastAPI Server" window or press Ctrl+C in it.

goto :eof

:serverTimeout
echo DEBUG: Condition TRUE (timeout reached via goto :serverTimeout)
echo.
echo Server did not become available at %FULL_WEBSITE_URL% after %MAX_ATTEMPTS% attempts (%MAX_ATTEMPTS% seconds).
echo Please check the 'FastAPI Server' window for any error messages.
pause

endlocal
goto :eof
