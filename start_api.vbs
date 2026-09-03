Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\ACC-2\amocrm-analytics"
WshShell.Run """C:\Users\ACC-2\amocrm-analytics\.venv\Scripts\python.exe"" -m uvicorn api_server:app --host 0.0.0.0 --port 8090", 0, False
