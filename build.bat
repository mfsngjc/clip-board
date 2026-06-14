@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\\Scripts\\python.exe" (
    py -3 -m venv .venv
)
".venv\\Scripts\\python.exe" -m pip install -e .
".venv\\Scripts\\python.exe" -m pip install nuitka ordered-set zstandard
".venv\\Scripts\\pyside6-deploy.exe" main.py --name "Clip Board"

