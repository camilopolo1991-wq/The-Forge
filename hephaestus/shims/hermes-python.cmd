@echo off
rem hermes-python.cmd: a stable name for the Hermes interpreter (Windows form; hermes-python is the POSIX sh form).
rem Rule: HERMES_PY if set and an existing file; else the newest python.exe under
rem %LOCALAPPDATA%\hermes\tools\python-*\ (newest by the version in the folder name, compared as numbers);
rem none: one line on stderr, exit 3. Single argument --which prints the resolved path, exit 0.
rem Otherwise runs the resolved interpreter with every argument and returns its exit code.
setlocal EnableDelayedExpansion
set "PY="
if defined HERMES_PY if exist "%HERMES_PY%" set "PY=%HERMES_PY%"
if not defined PY (
  set "BESTKEY="
  for /d %%D in ("%LOCALAPPDATA%\hermes\tools\python-*") do (
    if exist "%%D\python.exe" (
      set "NAME=%%~nxD"
      set "VER=!NAME:python-=!"
      for /f "tokens=1-3 delims=.+" %%a in ("!VER!") do (
        set "A=000000%%a"
        set "B=000000%%b"
        set "C=000000%%c"
        set "KEY=!A:~-6!!B:~-6!!C:~-6!"
        if not defined BESTKEY (
          set "BESTKEY=!KEY!"
          set "PY=%%D\python.exe"
        ) else if "!KEY!" GTR "!BESTKEY!" (
          set "BESTKEY=!KEY!"
          set "PY=%%D\python.exe"
        )
      )
    )
  )
)
if not defined PY (
  echo hermes-python: no interpreter found 1>&2
  exit /b 3
)
if "%~1"=="--which" if "%~2"=="" (
  echo !PY!
  exit /b 0
)
endlocal & "%PY%" %*
exit /b %ERRORLEVEL%
