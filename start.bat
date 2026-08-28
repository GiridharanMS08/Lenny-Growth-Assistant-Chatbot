@echo off
setlocal

REM ========================================
REM Lenny Growth Assistant Startup Script
REM ========================================

cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS=%~dp0requirements.txt"

echo ========================================
echo       Lenny Growth Assistant
echo ========================================
echo.

REM ----------------------------------------
REM Check System Python
REM ----------------------------------------
echo Checking Python...

python --version >nul 2>&1

if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not added to PATH.
    echo.
    pause
    exit /b 1
)

echo Python found.
echo.

REM ----------------------------------------
REM Create Virtual Environment
REM ----------------------------------------
if not exist "%PYTHON_EXE%" (
    echo Creating virtual environment...

    python -m venv "%VENV_DIR%"

    if errorlevel 1 (
        echo.
        echo ERROR: Could not create virtual environment.
        pause
        exit /b 1
    )

    echo Virtual environment created.
) else (
    echo Virtual environment already exists.
)

echo.

REM ----------------------------------------
REM Check requirements.txt
REM ----------------------------------------
if not exist "%REQUIREMENTS%" (
    echo.
    echo ERROR: requirements.txt was not found.
    echo Expected location:
    echo %REQUIREMENTS%
    echo.
    pause
    exit /b 1
)

REM ----------------------------------------
REM Upgrade pip
REM ----------------------------------------
echo Checking pip...

"%PYTHON_EXE%" -m pip install --upgrade pip

if errorlevel 1 (
    echo.
    echo ERROR: Could not upgrade pip.
    pause
    exit /b 1
)

echo.

REM ----------------------------------------
REM Install Python Requirements
REM ----------------------------------------
echo Installing/checking Python requirements...

"%PYTHON_EXE%" -m pip install -r "%REQUIREMENTS%"

if errorlevel 1 (
    echo.
    echo ERROR: Requirements installation failed.
    pause
    exit /b 1
)

echo.
echo Python requirements are ready.
echo.

REM ----------------------------------------
REM Verify rank_bm25
REM ----------------------------------------
echo Verifying rank_bm25...

"%PYTHON_EXE%" -c "from rank_bm25 import BM25Okapi; print('rank_bm25 OK')"

if errorlevel 1 (

    echo.
    echo rank_bm25 is NOT available.
    echo Installing rank-bm25...

    "%PYTHON_EXE%" -m pip install --upgrade --force-reinstall rank-bm25

    if errorlevel 1 (
        echo.
        echo ERROR: Could not install rank-bm25.
        pause
        exit /b 1
    )

    echo.
    echo Verifying rank_bm25 again...

    "%PYTHON_EXE%" -c "from rank_bm25 import BM25Okapi; print('rank_bm25 OK')"

    if errorlevel 1 (
        echo.
        echo ERROR: rank_bm25 is still not available.
        pause
        exit /b 1
    )
)

echo.
echo rank_bm25 is ready.
echo.

REM ----------------------------------------
REM Show Python Being Used
REM ----------------------------------------
echo ========================================
echo Backend Python Environment:
"%PYTHON_EXE%" -c "import sys; print(sys.executable)"
echo ========================================
echo.

REM ----------------------------------------
REM Check Node.js
REM ----------------------------------------
echo Checking Node.js...

node --version >nul 2>&1

if errorlevel 1 (
    echo.
    echo ERROR: Node.js is not installed or not added to PATH.
    echo.
    pause
    exit /b 1
)

echo Node.js found.
echo.

REM ----------------------------------------
REM Check Ollama
REM ----------------------------------------
echo Checking Ollama...

ollama --version >nul 2>&1

if errorlevel 1 (

    echo.
    echo ========================================
    echo Ollama is not installed.
    echo Opening Ollama download page...
    echo ========================================
    echo.

    start "" "https://ollama.com/download"

    echo Please install Ollama.
    echo.
    echo After installation:
    echo 1. Close this window
    echo 2. Run this START.bat file again
    echo.

    pause
    exit /b 1
)

echo Ollama found.
echo.

REM ----------------------------------------
REM Select AI Model
REM ----------------------------------------

:SELECT_MODEL

echo ========================================
echo          SELECT AI MODEL
echo ========================================
echo.
echo A. Qwen3 1.7B - Fastest / Low RAM
echo B. Qwen3 4B   - Balanced
echo C. Qwen3 8B   - Best Quality / More RAM
echo.
echo ========================================
echo.

set /p "MODEL_CHOICE=Enter your choice (A, B, or C): "

if /I "%MODEL_CHOICE%"=="A" (
    set "MODEL=qwen3:1.7b"
    set "MODEL_NAME=Qwen3 1.7B"
) else if /I "%MODEL_CHOICE%"=="B" (
    set "MODEL=qwen3:4b"
    set "MODEL_NAME=Qwen3 4B"
) else if /I "%MODEL_CHOICE%"=="C" (
    set "MODEL=qwen3:8b"
    set "MODEL_NAME=Qwen3 8B"
) else (
    echo.
    echo Invalid choice.
    echo Please select A, B, or C.
    echo.
    goto SELECT_MODEL
)

echo.
echo ========================================
echo Selected Model: %MODEL_NAME%
echo Ollama Model:   %MODEL%
echo ========================================
echo.

REM ----------------------------------------
REM Check Selected Ollama Model
REM ----------------------------------------
echo Checking if %MODEL% is installed...

ollama list | findstr /I /C:"%MODEL%" >nul

if errorlevel 1 (

    echo.
    echo %MODEL% is not installed.
    echo Downloading model...
    echo.

    ollama pull %MODEL%

    if errorlevel 1 (
        echo.
        echo ERROR: Could not download %MODEL%.
        echo Please check your internet connection.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo %MODEL_NAME% is ready!
echo ========================================
echo.

REM Make the selected model available to the FastAPI child process.
set "OLLAMA_MODEL=%MODEL%"

REM ----------------------------------------
REM Check PostgreSQL Configuration
REM ----------------------------------------
echo Checking PostgreSQL configuration...

REM The backend package is under .\backend, so run this check from that directory.
pushd "%~dp0backend"
"%PYTHON_EXE%" -c "from app.config import settings; from sqlalchemy import create_engine, text; e=create_engine(settings.database_url, pool_pre_ping=True); c=e.connect(); c.execute(text('SELECT 1')); c.close(); print('PostgreSQL connection OK')"
set "DB_CHECK_ERROR=%ERRORLEVEL%"
popd

if not "%DB_CHECK_ERROR%"=="0" (
    echo.
    echo ERROR: PostgreSQL configuration/connection check failed.
    echo.
    echo Make sure PostgreSQL is running and DATABASE_URL is valid.
    echo Set DATABASE_URL in .env or .env.example.
    echo Example:
    echo postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/lenny
    echo.
    pause
    exit /b 1
)

echo.

REM ----------------------------------------
REM Check Backend Folder
REM ----------------------------------------
if not exist "%~dp0backend" (
    echo.
    echo ERROR: Backend folder not found.
    echo Expected location:
    echo %~dp0backend
    echo.
    pause
    exit /b 1
)

REM ----------------------------------------
REM Final Backend Dependency Test
REM ----------------------------------------
echo Performing final backend dependency test...

"%PYTHON_EXE%" -c "from rank_bm25 import BM25Okapi; print('rank_bm25 verified for backend')"

if errorlevel 1 (
    echo.
    echo ERROR: rank_bm25 cannot be imported.
    echo.
    pause
    exit /b 1
)

echo.

REM ----------------------------------------
REM Start Backend
REM ----------------------------------------
echo ========================================
echo Starting Backend...
echo ========================================
echo.

start "Lenny Backend" cmd /k "cd /d ""%~dp0backend"" && ""%PYTHON_EXE%"" -m uvicorn app.main:app --reload"

echo Backend startup command sent.
echo.

REM ----------------------------------------
REM Check Frontend
REM ----------------------------------------
if exist "%~dp0frontend\package.json" (

    echo Checking frontend...

    REM Install dependencies only if node_modules
    REM folder does not exist
    if not exist "%~dp0frontend\node_modules" (

        echo.
        echo Installing frontend dependencies...
        echo.

        pushd "%~dp0frontend"

        call npm install

        if errorlevel 1 (

            popd

            echo.
            echo ERROR: Frontend dependency installation failed.
            echo.
            pause
            exit /b 1
        )

        popd

        echo.
        echo Frontend dependencies installed.
        echo.

    ) else (

        echo Frontend dependencies already exist.
        echo.
    )

    REM ----------------------------------------
    REM Start Frontend
    REM ----------------------------------------
    echo Starting frontend...

    start "Lenny Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

    echo Frontend startup command sent.

) else (

    echo.
    echo WARNING: frontend\package.json was not found.
    echo Frontend will not be started.
    echo.

)

REM ----------------------------------------
REM Startup Complete
REM ----------------------------------------

echo.
echo ========================================
echo         STARTING COMPLETE
echo ========================================
echo.
echo Backend:
echo http://127.0.0.1:8000
echo.
echo Frontend:
echo http://localhost:5173
echo.
echo Knowledge Ingestion:
echo WARNING: This may overwrite existing data.
echo http://127.0.0.1:8000/docs
echo.
echo Selected AI Model:
echo %MODEL_NAME%
echo.
echo ========================================

pause
