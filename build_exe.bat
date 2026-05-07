@echo off
echo Installing PyInstaller...
pip install pyinstaller

echo Packaging Realtime Log Splitter App...
pyinstaller --noconfirm --onefile --windowed --icon "Reference_app\app_icon.ico" --name "Realtime_Log_Splitter" --add-data "Reference_app\tn_logo.png;Reference_app" "Reference_app\realtime_splitter_app.py"

echo Moving executable to rawlogs folder...
if not exist rawlogs mkdir rawlogs
move dist\Realtime_Log_Splitter.exe rawlogs\

echo Cleaning up build files...
rmdir /s /q build
rmdir /s /q dist
del Realtime_Log_Splitter.spec

echo Build complete! The executable is located in the rawlogs folder.
pause
