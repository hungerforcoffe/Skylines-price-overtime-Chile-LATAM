@echo off
REM ──────────────────────────────────────────────────────────
REM  crear_tarea_diaria.bat
REM  Crea una tarea en Windows Task Scheduler para correr
REM  scraper_con_bd.py todos los días a las 9:00 AM
REM
REM  INSTRUCCIONES:
REM  1. Edita las rutas PYTHON_PATH y SCRIPT_DIR abajo
REM  2. Ejecuta este .bat como Administrador (clic derecho → Ejecutar como admin)
REM ──────────────────────────────────────────────────────────

REM ── EDITA ESTAS DOS RUTAS ──────────────────────────────────
set PYTHON_PATH=C:\Python314\python.exe
set SCRIPT_DIR=C:\Users\pablo\OneDrive\Escritorio\Vs_projects\Skylines_project_Chile
REM ───────────────────────────────────────────────────────────

schtasks /create ^
  /tn "Skylines_Scraper_Diario" ^
  /tr "\"%PYTHON_PATH%\" \"%SCRIPT_DIR%\scraper_con_bd.py\"" ^
  /sc DAILY ^
  /st 09:00 ^
  /sd 01/01/2026 ^
  /ru "%USERNAME%" ^
  /f

if %ERRORLEVEL% == 0 (
    echo.
    echo [OK] Tarea creada exitosamente.
    echo      Se ejecutara todos los dias a las 09:00 AM
    echo      Nombre de tarea: Skylines_Scraper_Diario
    echo.
    echo Para verificar:
    echo   schtasks /query /tn "Skylines_Scraper_Diario"
    echo.
    echo Para correr manualmente ahora:
    echo   schtasks /run /tn "Skylines_Scraper_Diario"
    echo.
    echo Para eliminar la tarea:
    echo   schtasks /delete /tn "Skylines_Scraper_Diario" /f
) else (
    echo.
    echo [ERROR] No se pudo crear la tarea.
    echo Asegurate de ejecutar este .bat como Administrador.
)

pause
