@echo off
echo Building Office Messenger...
call venv\Scripts\activate.bat
pip install pyinstaller PyQt6 websocket-client html
pyinstaller --noconsole --onefile --icon=app_icon.ico --name="OfficeMessenger" message_client.py
echo Build complete! Check the dist folder for OfficeMessenger.exe
pause
