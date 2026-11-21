@echo off
chcp 65001 >nul
title Agora TDAH
cd /d "%~dp0"
set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" where python >nul 2>nul && set PY=python
if "%PY%"=="" (
  echo.
  echo  Python nao foi encontrado neste computador.
  echo  Instale em https://www.python.org/downloads/ marcando "Add Python to PATH"
  echo  e de dois cliques neste arquivo de novo.
  echo.
  pause
  exit /b 1
)
if not exist "dados\agora.db" (
  echo Preparando o caso de demonstracao...
  %PY% server\seed_demo.py
)
start "" http://localhost:8765/app/
%PY% server\server.py
pause
