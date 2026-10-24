# Startar handläggar-UI:t om det inte redan kör och öppnar det i webbläsaren.
#
# Används av skrivbordsgenvägen (scripts/web/install_desktop_shortcut.py), men går
# också att köra direkt:
#     powershell -ExecutionPolicy Bypass -File scripts\web\open_ui.ps1 [-Db demo|svc_test|lakebase] [-Port 8765]
#
# Servern startas i ett eget minimerat fönster – stäng det fönstret för att stoppa
# UI:t. Kör redan UI:t på porten öppnas bara webbläsaren. Servern binds alltid till
# 127.0.0.1 (02_system/handläggar-ui.md §2). Standard är demodatabasen; Lakebase
# bara uttryckligen, eftersom ändringar där sparas på riktigt.

param(
    [ValidateSet('demo', 'svc_test', 'lakebase')][string]$Db = 'demo',
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$url = "http://127.0.0.1:$Port/"
$title = 'Artificiellalecta'

function Show-Error([string]$message) {
    (New-Object -ComObject WScript.Shell).Popup($message, 0, $title, 16) | Out-Null
    exit 1
}

function Test-Ui {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
        return $response.Content -match 'Artificiellalecta'
    } catch {
        return $false
    }
}

# Projektets Pythonmiljö: .venv i repot, annars i huvudcheckouten (git worktree).
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $common = & git -C $repo rev-parse --path-format=absolute --git-common-dir 2>$null
    if ($common) { $python = Join-Path (Split-Path $common -Parent) '.venv\Scripts\python.exe' }
}
if (-not (Test-Path $python)) {
    Show-Error "Hittar inte projektets Pythonmiljö (.venv) för $repo.`nSkapa den enligt README och kör pip install -e .[dev]."
}

if (-not (Test-Ui)) {
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        Show-Error "Port $Port används redan av ett annat program.`nStäng det eller starta med en annan port (-Port)."
    }
    $window = "Artificiellalecta handläggar-UI ($Db) - stäng fönstret för att stoppa"
    $command = "title $window && `"$python`" scripts\web\start_ui.py --db $Db --port $Port"
    Start-Process -FilePath $env:ComSpec -ArgumentList '/c', $command -WorkingDirectory $repo -WindowStyle Minimized

    $deadline = (Get-Date).AddSeconds(90)
    while (-not (Test-Ui)) {
        if ((Get-Date) -gt $deadline) {
            Show-Error "Handläggar-UI:t svarade inte på $url inom 90 sekunder.`nSe det minimerade serverfönstret för felmeddelandet."
        }
        Start-Sleep -Milliseconds 500
    }
}

Start-Process $url
