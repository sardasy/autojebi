param(
    [Parameter(Mandatory=$true)][string]$DatabaseUrl,
    [string]$Python = 'python',
    [switch]$BackendOnly
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ports = if ($BackendOnly) { @(8002) } else { @(8002, 3002) }
foreach ($port in $ports) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start() } catch { throw "Port $port is busy; existing programs were not stopped." } finally { $listener.Stop() }
}
$pythonPath = (Get-Command $Python).Source
$nodePath = (Get-Command node).Source
$env:DATABASE_URL = $DatabaseUrl
$env:SCHEDULER_ENABLED = 'false'
$env:SCHEDULER_GRADE_ENABLED = 'false'
$env:LOG_LEVEL = 'WARNING'
$env:WORKSPACE_DATA_DIR = Join-Path $root 'data/workspace'
$env:UPLOAD_DIR = Join-Path $root 'data/workspace/uploads'
$env:HWP_TEMPLATE_ROOT = Join-Path $root 'data'
$env:FRONTEND_ORIGIN = 'http://127.0.0.1:3002'
$env:INTERNAL_API_BASE = 'http://127.0.0.1:8002'
$env:NEXT_PUBLIC_API_BASE = 'http://127.0.0.1:8002'
$env:NEXT_DIST_DIR = '.next-workspace'
$env:WORKSPACE_V2_ENABLED = 'true'
$logs = Join-Path $root 'data/workspace/logs'
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$apiArguments = @('-m','uvicorn','api.main:app','--host','127.0.0.1','--port','8002')
if (Test-Path -LiteralPath (Join-Path $root '.env') -PathType Leaf) {
    $apiArguments += @('--env-file', '.env')
}
$api = Start-Process -FilePath $pythonPath -ArgumentList $apiArguments -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'api.stdout.log') -RedirectStandardError (Join-Path $logs 'api.stderr.log')
$worker = Start-Process -FilePath $pythonPath -ArgumentList @('-m','api.workspace.supervisor','--split') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'supervisor.stdout.log') -RedirectStandardError (Join-Path $logs 'supervisor.stderr.log')
$web = $null
if (-not $BackendOnly) {
    $web = Start-Process -FilePath $nodePath -ArgumentList @('node_modules/next/dist/bin/next','dev','--hostname','127.0.0.1','--port','3002') -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'web.stdout.log') -RedirectStandardError (Join-Path $logs 'web.stderr.log')
}
[pscustomobject]@{ ApiPid=$api.Id; WorkerSupervisorPid=$worker.Id; WebPid=$web.Id; Url='http://127.0.0.1:3002/workspace' }
