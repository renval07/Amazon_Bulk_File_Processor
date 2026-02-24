@echo off
setlocal

cd /d "%~dp0"

if not defined APP_ENV set "APP_ENV=local"

echo Starting Streamlit with APP_ENV=%APP_ENV%...
echo URL: http://localhost:8501
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m streamlit run streamlit_app.py
) else (
    python -m streamlit run streamlit_app.py
)

if errorlevel 1 (
    echo.
    echo Failed to start Streamlit. Ensure dependencies are installed:
    echo   pip install -r requirements.txt
    exit /b 1
)

endlocal
