[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & uv venv --python 3.12 (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Création du venv impossible.' }
}
& uv pip install --python $python -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances impossible.' }
$runtime = Join-Path $root '.runtime\winapp-v0.7.0'
$winapp = Join-Path $runtime 'winapp.exe'
if (-not (Test-Path -LiteralPath $winapp)) {
    $archive = Join-Path $root '.runtime\winappcli-v0.7.0-x64.zip'
    New-Item -ItemType Directory -Force -Path (Split-Path $archive) | Out-Null
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri 'https://github.com/microsoft/winappCli/releases/download/v0.7.0/winappcli-x64.zip' -OutFile $archive
    $expected = '236e35173f85a88a62cb030bdc07db6590fb7790514d530a050482a0da80313b'
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) { throw 'Empreinte WinApp invalide.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
}
& $python (Join-Path $root 'manage.py') init
if ($LASTEXITCODE -ne 0) { throw 'Initialisation impossible.' }
# State holds DPAPI credentials, logs and the Codex config backup.
$state = Join-Path $root 'state'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $state /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Protection du dossier state impossible.' }
& $python (Join-Path $root 'manage.py') register
if ($LASTEXITCODE -ne 0) { throw 'Enregistrement Codex impossible.' }
Write-Output 'Installation terminée. Lancer Start-Admin.ps1 et accepter UAC.'
