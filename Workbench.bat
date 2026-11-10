@echo off
rem Retroport Workbench x64: browse retail's items, sets and mounts and install them into the x64 client
rem (http://127.0.0.1:8335/ in your browser).
rem The first run needs the installs: Workbench.bat --bfa "<BfA install>" --retail "<retail install>"
rem   --client "<x64 client>" --dbd "<WoWDBDefs\definitions>" --listfile "<listfile.csv>"
rem Later runs remember them. Close this window to stop it.
cd /d "%~dp0"
python -m retroport.cli workbench %*
if errorlevel 1 pause
