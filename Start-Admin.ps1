[CmdletBinding()]
param([switch]$Elevated, [switch]$TestNotepad)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Exécuter Install.ps1 avant le démarrage.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    if ($Elevated) { throw 'La demande UAC ne nous a pas donné les droits administrateur.' }
    & $python (Join-Path $root 'manage.py') health --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Output 'Le serveur élevé est déjà actif.'
        if ($TestNotepad) { throw 'Pour ouvrir le Bloc-notes de test, arrêter le serveur puis relancer avec -TestNotepad.' }
        exit 0
    }
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Elevated'
    if ($TestNotepad) { $arguments += ' -TestNotepad' }
    $launcher = Start-Process -FilePath "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -PassThru
    # Wait only for the launcher. Start-Process -Wait also waits for its server child.
    $launcher.WaitForExit()
    & $python (Join-Path $root 'manage.py') health --wait 10
    if ($LASTEXITCODE -ne 0) { throw 'Le serveur ne répond pas après UAC; consulter state/server-bootstrap.err.log.' }
    exit 0
}
# Admin process stays in the interactive user's session. No scheduled task or service.
$config = Get-Content -Raw -LiteralPath (Join-Path $root 'config.json') | ConvertFrom-Json
$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort $config.port -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw 'Le port est déjà occupé. Vérifier le serveur avant de relancer.' }
$state = Join-Path $root 'state'
$arguments = '"' + (Join-Path $root 'server.py') + '"'
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state 'server-bootstrap.out.log') -RedirectStandardError (Join-Path $state 'server-bootstrap.err.log')
& $python (Join-Path $root 'manage.py') health --wait 20
if ($LASTEXITCODE -ne 0) { throw 'Échec du serveur élevé. Consulter state/server-bootstrap.err.log.' }
if ($TestNotepad) {
    $testFile = Join-Path $state 'Test-WinApp-Admin.txt'
    [IO.File]::WriteAllText($testFile, "WinApp admin MCP : test élevé.`r`n", [Text.UTF8Encoding]::new($false))
    Start-Process -FilePath "$env:WINDIR\System32\notepad.exe" -ArgumentList ('"' + $testFile + '"')
}
Write-Output "Serveur WinApp MCP administrateur démarré (PID $($process.Id))."
