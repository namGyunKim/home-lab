Remove-Item -Path build -Recurse -Force
Remove-Item -Path dist -Recurse -Force
pyinstaller --onefile --noconsole .\guild_builder.py
