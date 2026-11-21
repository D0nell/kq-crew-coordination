@echo off
setlocal
set PGSVC=C:\Program Files\PostgreSQL\18\bin
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p 5433 -d postgres -c "SELECT datname FROM pg_database ORDER BY 1;" -q
