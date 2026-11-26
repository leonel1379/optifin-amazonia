@echo off
chcp 65001 >nul
title OptiFin Amazonia
cd /d "%~dp0"

rem ============================================================
rem  OptiFin Amazonia - arranque con un clic (Windows)
rem  1a vez: busca Python, crea el entorno e instala bibliotecas.
rem  Siguientes veces: abre el programa directamente.
rem ============================================================

if exist ".venv\instalado.ok" goto EJECUTAR

echo ============================================================
echo   OptiFin Amazonia - preparando el programa (solo la 1a vez)
echo   Tarda de 1 a 3 minutos y necesita conexion a internet.
echo ============================================================
echo.

set "PY="
for %%V in (3.14 3.13 3.12 3.11) do if not defined PY (
  py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY goto SIN_PYTHON

echo [1/3] Python encontrado:
%PY% --version
echo [2/3] Creando el entorno del programa (.venv)...
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv || goto ERROR
)
echo [3/3] Instalando bibliotecas...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto ERROR_PIP
echo ok> ".venv\instalado.ok"
echo.
echo Instalacion completa.
echo.

:EJECUTAR
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 pause
exit /b

:SIN_PYTHON
echo No se encontro Python 3.11 o superior en este equipo.
where winget >nul 2>nul && (
  echo Instalando Python 3.12 automaticamente...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  echo.
  echo Python quedo instalado. Cierre esta ventana y haga doble clic otra vez en INICIAR.bat
  pause
  exit /b
)
echo Descargue Python 3.12 desde la pagina que se abrira, marque "Add python.exe to PATH",
echo instalelo y vuelva a hacer doble clic en INICIAR.bat
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:ERROR
echo [ERROR] No se pudo crear el entorno del programa.
pause
exit /b 1

:ERROR_PIP
echo [ERROR] No se pudieron instalar las bibliotecas. Revise su conexion a internet
echo y vuelva a hacer doble clic en INICIAR.bat
pause
exit /b 1
