@echo off
rem Retroport Workbench 32-bit: browse retail's items, sets and mounts and install them into the 32-bit
rem client (http://127.0.0.1:8337/ in your browser).
rem The first run needs the installs: Workbench.bat --bfa "<BfA install>" --retail "<retail install>"
rem   --client "<32-bit client>" --dbd "<WoWDBDefs\definitions>" --listfile "<listfile.csv>"
rem Later runs remember them. Close this window to stop it.
cd /d "%~dp0"
python -m retroport.cli workbench %*
if errorlevel 1 pause
