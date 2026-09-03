Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\ACC-2\amocrm-analytics"
WshShell.Run """C:\Users\ACC-2\amocrm-analytics\.venv\Scripts\python.exe"" main.py --no-send", 0, False
