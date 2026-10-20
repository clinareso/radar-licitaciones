@echo off
rem Actualiza data.json con las licitaciones vigentes de todas las fuentes.
rem La tarea programada diaria hace esto y además republica el dashboard.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python collector.py
pause
