param([string]$Python = 'python', [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not [Environment]::UserInteractive -or (Get-Process -Id $PID).SessionId -eq 0) {
    throw 'Start HWP Worker in a signed-in interactive Windows session.'
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port already occupied. Inspect the existing Worker; do not start another.'
}
$env:WORKSPACE_DATA_DIR = Join-Path $root 'data/workspace'
$env:HWP_TEMPLATE_ROOT = Join-Path $root 'data'
$env:HWP_SOURCE_ROOT = Join-Path $root 'data/workspace/uploads'
$env:HWP_OUTPUT_ROOT = Join-Path $root 'data/workspace/exports'
$log = Join-Path $root 'data/workspace/logs'
New-Item -ItemType Directory -Path $log -Force | Out-Null
Push-Location $root
try {
    $diagnostic = & $Python -m api.hwp_worker --check
    if ($LASTEXITCODE -ne 0) { throw 'HWP diagnostic failed.' }
    if (($diagnostic | ConvertFrom-Json).available -ne $true) {
        throw 'HWP is not available. Check the read-only diagnostic before starting.'
    }
    # create_app validates the secret, roots and recovery state before COM requests.
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $process = Start-Process -FilePath $Python -ArgumentList '-m', 'api.hwp_worker', '--port', $Port -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$log/hwp-$stamp.out.log" -RedirectStandardError "$log/hwp-$stamp.err.log" -PassThru
    Start-Sleep -Seconds 2
    $process.Refresh()
    if ($process.HasExited) { throw 'Worker startup failed. Check the sanitized startup log.' }
    [PSCustomObject]@{pid=$process.Id; port=$Port; log_prefix="$log/hwp-$stamp"}
} finally { Pop-Location }
