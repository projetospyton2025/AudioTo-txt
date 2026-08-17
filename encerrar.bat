@echo off
setlocal
cd /d "%~dp0"
echo Encerrando AudioTo-txt...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'SilentlyContinue';" ^
  "$root = [regex]::Escape('%~dp0');" ^
  "$ids = New-Object System.Collections.Generic.HashSet[int];" ^
  "Get-NetTCPConnection -LocalPort 5000 -State Listen | ForEach-Object { [void]$ids.Add([int]$_.OwningProcess) };" ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -and $_.CommandLine -match $root -and $_.CommandLine -match 'app\.py' } | ForEach-Object { [void]$ids.Add([int]$_.ProcessId) };" ^
  "if ($ids.Count -eq 0) { Write-Host 'AudioTo-txt nao estava em execucao.'; exit 0 };" ^
  "foreach ($id in $ids) { if ($id -gt 0) { Stop-Process -Id $id -Force; Write-Host ('Encerrado PID ' + $id) } };" ^
  "Write-Host 'AudioTo-txt encerrado.'"

echo.
pause
