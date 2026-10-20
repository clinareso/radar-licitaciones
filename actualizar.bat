@echo off
rem Baja la última versión del radar desde GitHub y abre el dashboard en este computador.
rem La recolección diaria la hace GitHub; no hace falta correr el recolector aquí.
cd /d "%~dp0"
git pull --quiet
start "" http://localhost:8000/dashboard.html
echo Dashboard en http://localhost:8000/dashboard.html  (cierra esta ventana para detenerlo)
python -m http.server 8000
