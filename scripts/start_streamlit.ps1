param(
    [int]$Port = 8502
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PythonExe = "C:\Users\86186\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$LogPath = Join-Path $ProjectRoot "results\streamlit.log"

Set-Location $ProjectRoot
& $PythonExe -m streamlit run app.py `
    --server.headless=true `
    --server.port=$Port `
    --browser.gatherUsageStats=false *> $LogPath
