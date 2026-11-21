@echo off
setlocal
set PGSVC=C:\Program Files\PostgreSQL\18\bin
set PGDATA=C:\postgres_data\pgdata

echo === PostgreSQL 18 prep ===
if not exist "%PGDATA%" (
  echo initdb ...
  "%PGSVC%\initdb.exe" -U postgres -D "%PGDATA%" --auth=trust --no-locale
  if errorlevel 1 exit /b 1
)

echo starting postgres on port 5433 ...
"%PGSVC%\pg_ctl.exe" -D "%PGDATA%" start -l "%PGDATA%\server.log" -w -t 300 -o "-p 5433"
if errorlevel 1 exit /b 1

echo creating databases ...
"%PGSVC%\createdb.exe" -U postgres -h localhost -p 5432 kq_crew_coordination
if errorlevel 1 exit /b 1
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p 5433 -d postgres -c "DROP DATABASE IF EXISTS kq_crew_coordination WITH (FORCE);" -q
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p 5433 -d postgres -c "CREATE DATABASE kq_crew_coordination;" -q
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p 5433 -d postgres -c "DROP DATABASE IF EXISTS kq_test WITH (FORCE);" -q
"%PGSVC%\psql.exe" -U postgres -h 127.0.0.1 -p 5433 -d postgres -c "CREATE DATABASE kq_test;" -q

echo DONE
