# Startar och öppnar handläggar-UI:t. Vanlig start: Lakebase på 8765.
# Demo använder 8767 och test 8766. En körande server återanvänds bara om
# databasläget kan verifieras. Inga servrar stoppas och ingen data flyttas.
param(
    [ValidateSet('demo', 'svc_test', 'lakebase')][string]$Db = 'lakebase',
    [ValidateRange(1, 65535)][int]$Port
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $PSBoundParameters.ContainsKey('Port')) {
    $Port = @{ lakebase = 8765; svc_test = 8766; demo = 8767 }[$Db]
}
$url = "http://127.0.0.1:$Port/"
$title = 'Artificiellalecta'

function Show-Error([string]$message) {
    (New-Object -ComObject WScript.Shell).Popup($message, 0, $title, 16) | Out-Null
    exit 1
}

function Get-UiDatabase {
    try {
        $response = Invoke-RestMethod -Uri ($url + '_instance') -TimeoutSec 2
    } catch {
        return $null
    }
    if ($response.application -ne 'artificiellalecta-handlaggare' -or
        $response.database -notin @('demo', 'svc_test', 'lakebase')) {
        Show-Error "Port $Port svarar med en okänd app eller version. Stäng den eller välj en annan port (-Port)."
    }
    if ($response.database -ne $Db) {
        Show-Error "Fel databas på port ${Port}: appen använder '$($response.database)', men du valde '$Db'.`nStäng den gamla servern och starta igen, eller välj en annan port (-Port). Ingen databas har bytts."
    }
    return $response.database
}

if (Get-UiDatabase) {
    Start-Process $url
    exit 0
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Show-Error "Port $Port används redan av ett program som inte kan verifiera databasläget (t.ex. en äldre UI-version).`nStäng den gamla servern eller välj en annan port (-Port)."
}

# .venv i den egna checkouten, annars i huvudcheckouten (git worktree).
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $common = & git -C $repo rev-parse --path-format=absolute --git-common-dir 2>$null
    if ($common) { $python = Join-Path (Split-Path $common -Parent) '.venv\Scripts\python.exe' }
}
if (-not (Test-Path $python)) {
    Show-Error "Hittar inte projektets Pythonmiljö (.venv) för $repo. Skapa den enligt README."
}

$server = Start-Process -FilePath $python -ArgumentList @('scripts\web\start_ui.py', '--db', $Db, '--port', $Port) -WorkingDirectory $repo -WindowStyle Hidden -PassThru
$deadline = (Get-Date).AddSeconds(30)
while (-not (Get-UiDatabase)) {
    if ($server.HasExited) {
        Show-Error "Handläggar-UI:t kunde inte starta i läget '$Db'. Kontrollera .env och Pythonmiljön. Starta scripts/web/start_ui.py --db $Db --port $Port i en terminal för detaljer. Ingen annan databas används."
    }
    if ((Get-Date) -gt $deadline) {
        Show-Error "Handläggar-UI:t svarade inte på $url inom 30 sekunder. Kontrollera servern innan du försöker igen."
    }
    Start-Sleep -Milliseconds 500
}

Start-Process $url
