Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\ACC-2\amocrm-analytics"
WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & "C:\Users\ACC-2\amocrm-analytics\tunnel_runner.ps1" & Chr(34), 0, False
