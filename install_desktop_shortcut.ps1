$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat = Join-Path $Root "START_KUH_AI.bat"
$w = New-Object -ComObject WScript.Shell
foreach ($d in @(
  [Environment]::GetFolderPath("Desktop"),
  "C:\Users\ACC-2\Desktop",
  "C:\Users\ACC-2\OneDrive\Desktop"
)) {
  if (-not (Test-Path $d)) { continue }
  $lnk = Join-Path $d "KUH AI.lnk"
  $sc = $w.CreateShortcut($lnk)
  $sc.TargetPath = $bat
  $sc.WorkingDirectory = $Root
  $sc.WindowStyle = 7
  $sc.Description = "KUH AI Desktop - medical assistant"
  $icon = "C:\Program Files\Google\Chrome\Application\chrome.exe"
  if (Test-Path $icon) { $sc.IconLocation = "$icon,0" }
  $sc.Save()
  Write-Host "Shortcut: $lnk"
}

# Startup optional
$startup = [Environment]::GetFolderPath("Startup")
$sl = Join-Path $startup "KUH-AI-Desktop.lnk"
$sc2 = $w.CreateShortcut($sl)
$sc2.TargetPath = $bat
$sc2.WorkingDirectory = $Root
$sc2.WindowStyle = 7
$sc2.Save()
Write-Host "Startup: $sl"
Write-Host "Done"
