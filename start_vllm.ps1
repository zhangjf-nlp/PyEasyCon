$ErrorActionPreference = "Continue"
$host.UI.RawUI.WindowTitle = "vLLM Qwen3-VL Launcher"

Write-Host "=========================================="
Write-Host "  vLLM + Qwen3-VL-2B Launcher"
Write-Host "=========================================="
Write-Host ""

Write-Host "[1/2] Checking vLLM service..."
try {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -eq 200) {
        Write-Host "vLLM already running! http://localhost:8000" -ForegroundColor Green
        Write-Host ""
        Read-Host "Press Enter to exit"
        exit 0
    }
}
catch {
    Write-Host "  Service not running, starting..." -ForegroundColor Gray
}

Write-Host ""
Write-Host "[2/2] Starting vLLM via start_vllm.sh in WSL"
Write-Host "------------------------------------------"
Write-Host "  First load takes ~30-60 seconds."
Write-Host "  Wait for 'Application startup complete'."
Write-Host "  Close this window to stop vLLM."
Write-Host "------------------------------------------"
Write-Host ""

wsl -e bash -c "cd ~/vllm-qwen3vl; bash start_vllm.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "vLLM exited with code: $LASTEXITCODE" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check:"
    Write-Host "  1. WSL installed: wsl --list -v"
    Write-Host "  2. start_vllm.sh exists: wsl -e ls ~/vllm-qwen3vl/start_vllm.sh"
    Write-Host "  3. Model downloaded: wsl -e ls ~/.cache/modelscope/hub/models/Qwen/Qwen3-VL-2B-Instruct-FP8/"
}

Write-Host ""
Write-Host "vLLM service stopped."
Read-Host "Press Enter to exit"
