@echo off
setlocal
set PGSVC=C:\Program Files\PostgreSQL\18\bin
set PGPASSWORD=***
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p 5434 -d kq_crew_coordination -c "SELECT current_database() AS db, 1 AS ok;"
