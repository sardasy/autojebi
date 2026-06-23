# autojebi 호스트 서비스 런처
# ------------------------------------------------------------------
# HWP 서류 처리를 쓰려면 API를 "호스트에서" 실행해야 한다(에이전트가 Windows COM 로컬 프로세스라
# 컨테이너에서는 경로/연결이 어긋남). 이 스크립트는 두 프로세스를 각각 "별도 창"에서 띄워
# 터미널/세션과 독립적으로 계속 떠 있게 한다.
#
#   1) milim-hwp-agent   (127.0.0.1:8000)   — HWP COM 브리지
#   2) autojebi API      (0.0.0.0:8001)     — uvicorn (pydantic이 .env에서 키 자동 로드)
#
# 전제: Docker로 Postgres(:5434) + Qdrant(:6333) + 프론트엔드(:3001)가 이미 떠 있어야 함.
#   docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml --env-file .env up -d db qdrant frontend
#
# 사용:  powershell -ExecutionPolicy Bypass -File scripts\start-host-services.ps1
# 종료:  각 창을 닫거나 Ctrl+C.
# ------------------------------------------------------------------
$ErrorActionPreference = "Stop"

$repo     = Split-Path -Parent $PSScriptRoot
$agentDir = "C:\Users\a\Desktop\milim-hwp-agent"

# 업로드/내보내기 저장소: Docker 바인드마운트(리포 data\)가 아닌 별도 호스트 폴더.
# (data\uploads는 compose 바인드마운트라 Docker Desktop이 점유 → 호스트 새 파일 쓰기가 실패함)
$uploadDir = "C:\Users\a\autojebi-data\uploads"
$exportDir = "C:\Users\a\autojebi-data\exports"
New-Item -ItemType Directory -Force -Path $uploadDir | Out-Null
New-Item -ItemType Directory -Force -Path $exportDir | Out-Null

if (-not (Test-Path $agentDir)) {
    Write-Warning "HWP 에이전트 폴더를 찾을 수 없습니다: $agentDir (경로를 확인하세요)"
}

# 1) HWP 에이전트 (별도 창, 127.0.0.1:8000)
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$agentDir'; Write-Host 'HWP agent :8000'; python run_api_server.py"
)

# 2) autojebi API (별도 창, 0.0.0.0:8001). 시크릿은 .env에서 자동 로드되므로 여기선 비-시크릿만 설정.
$apiCmd = @"
cd '$repo'
`$env:DATABASE_URL='postgresql+psycopg://autojebi:autojebi@localhost:5434/autojebi'
`$env:QDRANT_URL='http://localhost:6333'
`$env:HWP_AGENT_BASE_URL='http://127.0.0.1:8000'
`$env:UPLOAD_DIR='$uploadDir'
`$env:EXPORT_DIR='$exportDir'
`$env:FRONTEND_ORIGIN='http://localhost:3001'
`$env:SCHEDULER_ENABLED='true'
Write-Host 'autojebi API :8001'
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
"@
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $apiCmd)

Write-Host "두 창이 떴습니다. 확인:"
Write-Host "  curl http://localhost:8000/health"
Write-Host "  curl http://localhost:8001/healthz"
Write-Host "  curl http://localhost:8001/documents/hwp-agent/health"
