$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'manage.py') stop
if ($LASTEXITCODE -ne 0) { throw 'Arrêt impossible; vérifier que le serveur est actif.' }
