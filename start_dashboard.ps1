$ErrorActionPreference = "SilentlyContinue"
$busy = Get-NetTCPConnection -LocalPort 8000 -State Listen
if ($busy) { exit 0 }
$py = "C:\Users\1\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }
Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList "app.py" -WorkingDirectory "C:\Users\1\Documents\Default Project"
