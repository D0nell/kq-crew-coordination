@echo off
setlocal
set PGSVC=C:\Program Files\PostgreSQL\18\bin
set PGDATA=C:\postgres_utf8\pgdata
set PORT=5435

if exist "%PGDATA%" rmdir /s /q "%PGDATA%"
if not exist "%PGDATA%" mkdir "%PGDATA%"

echo initdb (UTF8) ...
"%PGSVC%\initdb.exe" -U postgres -D "%PGDATA%" --encoding=UTF8 --locale=C --auth=trust
if errorlevel 1 exit /b 1

echo starting postgres on port %PORT% ...
"%PGSVC%\pg_ctl.exe" -D "%PGDATA%" start -l "%PGDATA%\server.log" -w -t 300 -o "-p %PORT%"
if errorlevel 1 exit /b 1

echo creating databases ...
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p %PORT% -d postgres -c "DROP DATABASE IF EXISTS kq_crew_coordination WITH (FORCE);" -q
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p %PORT% -d postgres -c "CREATE DATABASE kq_crew_coordination;" -q
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p %PORT% -d postgres -c "DROP DATABASE IF EXISTS kq_test WITH (FORCE);" -q
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p %PORT% -d postgres -c "CREATE DATABASE kq_test;" -q

echo DONE
