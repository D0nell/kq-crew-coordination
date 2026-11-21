@echo off
setlocal
set PGSVC=C:\Program Files\PostgreSQL\18\bin
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p 5435 -d kq_crew_coordination -v ON_ERROR_STOP=1 -c "SELECT current_database() AS db, 1 AS ok;"
