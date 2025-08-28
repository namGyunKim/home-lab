Remove-Item -Path build -Recurse -Force
Remove-Item -Path dist -Recurse -Force
pyinstaller --onefile --noconsole .\abyss_scheduler.py
