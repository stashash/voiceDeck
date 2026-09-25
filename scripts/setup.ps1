# Мастер установки voiceDeck для Windows: Docker, модель, веса распознавания речи, .env, запуск стека.
# Запуск из корня репозитория: setup.cmd
# Без вопросов (для проверки и CI): setup.cmd -Model lmstudio|ollama|api|none -Yes [-ApiUrl URL -ApiModel ИМЯ -ApiKey КЛЮЧ]
# Работает во встроенном Windows PowerShell 5.1: PowerShell 7 не нужен.
param(
    [ValidateSet('', 'lmstudio', 'ollama', 'api', 'none')][string]$Model = '',
    [string]$ApiUrl = '',
    [string]$ApiModel = '',
    [string]$ApiKey = '',
    [switch]$Yes
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$AppUrl = 'http://localhost:8088'
$QwenKey = 'qwen/qwen3.8-27b'
$BgeUrl = 'https://huggingface.co/lm-kit/bge-m3-gguf/blob/main/bge-m3-Q8_0.gguf'
$LmStudioExe = Join-Path $env:LOCALAPPDATA 'Programs\LM Studio\LM Studio.exe'
$OllamaQwen = 'qwen3.8:27b'
# Своя модель поверх qwen3.8: у Ollama контекст 4096 по умолчанию, промпты designer длиннее
$OllamaModel = 'voicedeck-qwen3.8'
$DockerExe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'

function Show-Step([int]$n, [string]$text) { Write-Host ''; Write-Host "[$n/6] $text" -ForegroundColor Cyan }
function Show-Ok([string]$text) { Write-Host "  готово: $text" -ForegroundColor Green }
function Show-Note([string]$text) { Write-Host "  $text" -ForegroundColor Yellow }
function Stop-Setup([string]$text) {
    Write-Host ''
    Write-Host "  Остановлено: $text" -ForegroundColor Red
    Write-Host '  Исправьте и запустите setup.cmd снова: сделанные шаги он пропустит.'
    exit 1
}
function Confirm-Step([string]$question) {
    if ($Yes) { return $true }
    $answer = Read-Host "  $question [Д/н]"
    return [string]::IsNullOrWhiteSpace($answer) -or ($answer.Trim().ToLower() -in @('д', 'да', 'y', 'yes'))
}
function Test-Command([string]$name) { return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
# Windows PowerShell 5.1 превращает stderr внешней программы в ошибку: проверки идут через cmd.
function Test-Native([string]$commandLine) { cmd /c "$commandLine >nul 2>&1"; return ($LASTEXITCODE -eq 0) }
function Wait-For([int]$seconds, [scriptblock]$check) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $check) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}
function Update-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Find-Lms {
    $found = Get-Command lms -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $candidate = Join-Path $HOME '.lmstudio\bin\lms.exe'
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    return $null
}
function Find-Ollama {
    $found = Get-Command ollama -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $candidate = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    return $null
}
function Test-Gpu([string]$runner) {
    if (Test-Command nvidia-smi) {
        $vram = (cmd /c 'nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>nul') | ForEach-Object { [int]($_.Trim()) } | Measure-Object -Maximum
        if ($vram.Maximum -lt 22000) { Show-Note "Видеопамяти $([math]::Round($vram.Maximum / 1024)) ГБ: Qwen3.8 27B с контекстом 20k может не поместиться." }
        else { Show-Ok "видеокарта с $([math]::Round($vram.Maximum / 1024)) ГБ памяти" }
    } else {
        Show-Note 'Видеокарта NVIDIA не найдена: модель пойдёт на процессоре и будет отвечать минутами.'
        if (-not (Confirm-Step "Продолжить с $runner?")) { Stop-Setup 'выберите внешний API или режим без модели' }
    }
}
function Install-WithWinget([string]$id, [string]$title) {
    if (-not (Test-Command winget)) { Stop-Setup "нет winget, поставьте $title вручную и запустите мастер снова" }
    if (-not (Confirm-Step "Поставить $title через winget?")) { Stop-Setup "без $title этот путь не работает" }
    winget install -e --id $id --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Stop-Setup "winget не поставил $title (код $LASTEXITCODE)" }
    Update-Path
}
function Get-Http([string]$url, [hashtable]$headers = @{}) {
    try { return Invoke-WebRequest -Uri $url -Headers $headers -UseBasicParsing -TimeoutSec 10 } catch { return $null }
}
# .env: меняются только названные ключи, остальные строки остаются. Кодировка UTF-8 без BOM: иначе compose не прочтёт первый ключ.
function Set-EnvValues([hashtable]$values) {
    $path = Join-Path $Root '.env'
    if (-not (Test-Path -LiteralPath $path)) { Copy-Item -LiteralPath (Join-Path $Root '.env.example') -Destination $path }
    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in [IO.File]::ReadAllLines($path)) { $lines.Add($line) }
    foreach ($key in $values.Keys) {
        $index = -1
        for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match "^$([regex]::Escape($key))=") { $index = $i } }
        $entry = "$key=$($values[$key])"
        if ($index -ge 0) { $lines[$index] = $entry } else { $lines.Add($entry) }
    }
    [IO.File]::WriteAllText($path, (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
}

Write-Host 'Мастер установки voiceDeck' -ForegroundColor Cyan
Write-Host 'Шаги: Docker, модель, веса распознавания речи, настройки, запуск, проверка. Повторный запуск пропускает сделанное.'

# ---------- 1. Docker ----------
Show-Step 1 'Docker Desktop'
if (-not (Test-Command docker)) {
    Show-Note 'Docker Desktop не найден.'
    Install-WithWinget 'Docker.DockerDesktop' 'Docker Desktop'
    Show-Note 'Если установщик попросил перезагрузку, перезагрузите компьютер и запустите setup.cmd снова.'
}
if (-not (Test-Native 'docker info')) {
    if (Test-Path -LiteralPath $DockerExe) {
        Start-Process -FilePath $DockerExe
        Show-Note 'Запускаю Docker Desktop. При первом запуске примите соглашение в его окне. Жду до 5 минут.'
    }
    if (-not (Wait-For 300 { Test-Native 'docker info' })) {
        Stop-Setup 'Docker не отвечает: откройте Docker Desktop и дождитесь надписи Engine running'
    }
}
if (-not (Test-Native 'docker compose version')) { Stop-Setup 'нет docker compose: обновите Docker Desktop' }
Show-Ok 'Docker работает'

# ---------- 2. Модель ----------
Show-Step 2 'Модель'
while (-not $Model) {
    Write-Host '  1  LM Studio на этой машине: Qwen3.8 27B и bge-m3, около 18 ГБ, нужна видеокарта NVIDIA от 24 ГБ'
    Write-Host '  2  Ollama на этой машине: те же модели, около 19 ГБ, та же видеокарта'
    Write-Host '  3  Внешний OpenAI-совместимый API с Qwen3.8 27B, например инференс VK'
    Write-Host '  4  Без модели: готовые дизайн-системы и презентации, правка текста, скачивание'
    $choice = (Read-Host '  Выберите 1, 2, 3 или 4').Trim()
    $Model = @{ '1' = 'lmstudio'; '2' = 'ollama'; '3' = 'api'; '4' = 'none' }[$choice]
}
$envValues = @{}
if ($Model -eq 'lmstudio') {
    Test-Gpu 'LM Studio'
    if (-not (Find-Lms)) {
        if (-not (Test-Path -LiteralPath $LmStudioExe)) { Install-WithWinget 'ElementLabs.LMStudio' 'LM Studio' }
        if (Test-Path -LiteralPath $LmStudioExe) { Start-Process -FilePath $LmStudioExe }
        Show-Note 'Открываю LM Studio: при первом запуске он кладёт команду lms. Жду до 3 минут.'
        if (-not (Wait-For 180 { [bool](Find-Lms) })) { Stop-Setup 'не появилась команда lms: откройте LM Studio вручную один раз' }
    }
    $lms = Find-Lms
    & $lms server start
    Show-Note 'Скачиваю модели, если их ещё нет. Qwen3.8 27B весит около 17 ГБ.'
    & $lms get $QwenKey -y
    if ($LASTEXITCODE -ne 0) { Stop-Setup "не скачалась $QwenKey" }
    & $lms get $BgeUrl -y
    if ($LASTEXITCODE -ne 0) { Stop-Setup 'не скачались эмбеддинги bge-m3' }
    & (Join-Path $PSScriptRoot 'start-models.ps1')
    $envValues = @{
        DESIGNER_LLM_URL = 'http://host.docker.internal:1234/v1'; DESIGNER_LLM_MODEL = $QwenKey; DESIGNER_LLM_API_KEY = ''
        DESIGNER_LLM_PARALLEL = '4'
        EMBEDDING_BACKEND = 'ollama'; EMBEDDING_URL = 'http://host.docker.internal:1234/v1'; EMBEDDING_MODEL = 'text-embedding-bge-m3'
    }
    Show-Ok 'LM Studio с Qwen3.8 27B и bge-m3'
} elseif ($Model -eq 'ollama') {
    Test-Gpu 'Ollama'
    if (-not (Find-Ollama)) { Install-WithWinget 'Ollama.Ollama' 'Ollama' }
    $ollama = Find-Ollama
    if (-not $ollama) { Stop-Setup 'не найдена команда ollama: откройте Ollama один раз и запустите мастер снова' }
    if (-not (Get-Http 'http://127.0.0.1:11434/api/version')) {
        Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden
        if (-not (Wait-For 60 { [bool](Get-Http 'http://127.0.0.1:11434/api/version') })) { Stop-Setup 'Ollama не отвечает на 127.0.0.1:11434: откройте приложение Ollama' }
    }
    Show-Note "Скачиваю модели, если их ещё нет. $OllamaQwen весит около 18 ГБ."
    & $ollama pull $OllamaQwen
    if ($LASTEXITCODE -ne 0) { Stop-Setup "не скачалась $OllamaQwen" }
    & $ollama pull bge-m3
    if ($LASTEXITCODE -ne 0) { Stop-Setup 'не скачались эмбеддинги bge-m3' }
    $modelfile = Join-Path $env:TEMP 'voicedeck-qwen.Modelfile'
    [IO.File]::WriteAllText($modelfile, "FROM $OllamaQwen`nPARAMETER num_ctx 20480`n", (New-Object Text.UTF8Encoding($false)))
    & $ollama create $OllamaModel -f $modelfile
    if ($LASTEXITCODE -ne 0) { Stop-Setup "не создалась модель $OllamaModel" }
    # Ollama по умолчанию отвечает на один запрос за раз: designer не шлёт параллельных, чтобы Live не ждал очереди.
    $envValues = @{
        DESIGNER_LLM_URL = 'http://host.docker.internal:11434/v1'; DESIGNER_LLM_MODEL = $OllamaModel; DESIGNER_LLM_API_KEY = ''
        DESIGNER_LLM_PARALLEL = '1'
        EMBEDDING_BACKEND = 'ollama'; EMBEDDING_URL = 'http://host.docker.internal:11434/v1'; EMBEDDING_MODEL = 'bge-m3'
    }
    Show-Ok "Ollama с $OllamaQwen и bge-m3"
} elseif ($Model -eq 'api') {
    if (-not $ApiUrl) { $ApiUrl = (Read-Host '  Адрес API, например https://example.com/v1').Trim() }
    if (-not $ApiModel) {
        $ApiModel = (Read-Host "  Имя модели [$QwenKey]").Trim()
        if (-not $ApiModel) { $ApiModel = $QwenKey }
    }
    if (-not $ApiKey -and -not $Yes) {
        $secure = Read-Host '  Ключ API (Enter, если ключ не нужен)' -AsSecureString
        $ApiKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    }
    $ApiUrl = $ApiUrl.TrimEnd('/')
    $headers = @{}
    if ($ApiKey) { $headers['Authorization'] = "Bearer $ApiKey" }
    if (Get-Http "$ApiUrl/models" $headers) { Show-Ok "API отвечает: $ApiUrl" }
    else { Show-Note "API не ответил на $ApiUrl/models. Проверьте адрес и ключ; настройки всё равно запишу." }
    # Сервис работает в контейнере: localhost там свой, адрес хоста называется host.docker.internal.
    $containerUrl = $ApiUrl -replace '//(localhost|127\.0\.0\.1)([:/])', '//host.docker.internal$2'
    $envValues = @{
        DESIGNER_LLM_URL = $containerUrl; DESIGNER_LLM_MODEL = $ApiModel; DESIGNER_LLM_API_KEY = $ApiKey
        EMBEDDING_BACKEND = 'disabled'
    }
    Show-Note 'Эмбеддинги для Live берутся только из локальной сети: границы мыслей в речи пойдут по паузам.'
} else {
    $envValues = @{ EMBEDDING_BACKEND = 'disabled' }
    Show-Ok 'без модели: генерация и Live заработают, когда модель подключат и запустят мастер снова'
}

# ---------- 3. Веса распознавания речи ----------
Show-Step 3 'Веса распознавания речи'
& (Join-Path $PSScriptRoot 'setup-models.ps1')
Show-Ok 'GigaAM-v3, Silero VAD, sherpa-onnx'

# ---------- 4. Настройки ----------
Show-Step 4 'Настройки в .env'
$envValues['MODE'] = 'live'
$envValues['SLIDE_MODE'] = 'designer'
Set-EnvValues $envValues
Show-Ok '.env записан'

# ---------- 5. Запуск ----------
Show-Step 5 'Сборка и запуск контейнеров'
Show-Note 'Первая сборка идёт несколько минут.'
docker compose up --build -d
if ($LASTEXITCODE -ne 0) { Stop-Setup 'docker compose не поднял стек' }

# ---------- 6. Проверка ----------
Show-Step 6 'Проверка'
if (-not (Wait-For 600 { [bool](Get-Http 'http://127.0.0.1:8090/health') })) { Stop-Setup 'сервис designer не ответил: docker compose logs designer' }
if (-not (Wait-For 300 { [bool](Get-Http 'http://127.0.0.1:8088/health') })) { Stop-Setup 'сервис app не ответил: docker compose logs app' }
$health = (Get-Http 'http://127.0.0.1:8090/health').Content | ConvertFrom-Json
$systems = (Invoke-RestMethod -Uri 'http://127.0.0.1:8090/design-systems' -UseBasicParsing).ids.Count
$decks = (Invoke-RestMethod -Uri 'http://127.0.0.1:8090/decks' -UseBasicParsing).items.Count
Show-Ok "дизайн-систем: $systems, презентаций: $decks"
if ($health.model_ok) { Show-Ok 'модель отвечает: генерация и Live доступны' }
elseif ($Model -ne 'none') { Show-Note 'Модель пока не отвечает: проверьте LM Studio, Ollama или API. Просмотр и скачивание работают.' }

Write-Host ''
Write-Host "voiceDeck работает: $AppUrl" -ForegroundColor Green
Write-Host '  Остановить: docker compose stop. Запустить снова: docker compose start.'
if ($Model -eq 'lmstudio') { Write-Host '  После перезагрузки компьютера запустите setup.cmd снова: он загрузит модели в LM Studio и поднимет стек.' }
if (-not $Yes) { Start-Process $AppUrl }
