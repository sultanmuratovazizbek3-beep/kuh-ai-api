Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\ACC-2\amocrm-analytics"
WshShell.Run "cmd /c \"C:\Users\ACC-2\amocrm-analytics\start_always_online.bat\" nopause", 0, False
