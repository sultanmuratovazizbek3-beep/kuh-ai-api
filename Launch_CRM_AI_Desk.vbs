' CRM AI Desk — stable launcher (API + Worker + UI via Task Scheduler)
' Avoids Job Object kill when parent shell exits.
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)

pythonw = dir & "\.venv\Scripts\pythonw.exe"
python = dir & "\.venv\Scripts\python.exe"
If Not fso.FileExists(pythonw) Then pythonw = python
If Not fso.FileExists(python) Then
  MsgBox "CRM AI Desk: не найден .venv\Scripts\python.exe" & vbCrLf & dir, 16, "CRM AI Desk"
  WScript.Quit 1
End If

apiCmd = """" & python & """ """ & dir & "\api_main.py"""
wrkCmd = """" & python & """ """ & dir & "\worker_main.py"""
uiCmd  = """" & pythonw & """ """ & dir & "\ui_main.py"""

' Recreate ONCE tasks and run them (escape job / survive logoff of launcher)
On Error Resume Next
sh.Run "schtasks /Create /TN CRMAIDesk_API /TR " & apiCmd & " /SC ONCE /ST 00:00 /RL LIMITED /F", 0, True
sh.Run "schtasks /Create /TN CRMAIDesk_Worker /TR " & wrkCmd & " /SC ONCE /ST 00:00 /RL LIMITED /F", 0, True
sh.Run "schtasks /Create /TN CRMAIDesk_UI /TR " & uiCmd & " /SC ONCE /ST 00:00 /RL LIMITED /F", 0, True
sh.Run "schtasks /Run /TN CRMAIDesk_API", 0, False
WScript.Sleep 2500
sh.Run "schtasks /Run /TN CRMAIDesk_Worker", 0, False
WScript.Sleep 1200
sh.Run "schtasks /Run /TN CRMAIDesk_UI", 0, False
On Error GoTo 0
