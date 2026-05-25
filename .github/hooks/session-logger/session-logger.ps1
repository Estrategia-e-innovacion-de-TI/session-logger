param(
    [Parameter(Mandatory = $true)]
    [string]$Event
)

$ErrorActionPreference = 'Stop'

function Find-BashPath {
    $command = Get-Command bash -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:ProgramFiles 'Git\bin\bash.exe'),
        (Join-Path $env:ProgramFiles 'Git\usr\bin\bash.exe'),
        (Join-Path $env:ProgramW6432 'Git\bin\bash.exe'),
        (Join-Path $env:ProgramW6432 'Git\usr\bin\bash.exe')
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

$bashPath = Find-BashPath
if (-not $bashPath) {
    Write-Error 'No se encontro bash. Instala Git for Windows (Git Bash) o configura WSL para ejecutar session-logger.'
    exit 1
}

$scriptPath = Join-Path $PSScriptRoot 'session-logger.sh'
if (-not (Test-Path $scriptPath)) {
    Write-Error "No se encontro el script: $scriptPath"
    exit 1
}

if (-not $env:COPILOT_SESSION_LOGGER_LOKI_ENABLED) {
    $env:COPILOT_SESSION_LOGGER_LOKI_ENABLED = 'true'
}
if (-not $env:COPILOT_SESSION_LOGGER_LOKI_ENDPOINT) {
    $env:COPILOT_SESSION_LOGGER_LOKI_ENDPOINT = 'http://localhost:3100/loki/api/v1/push'
}
if (-not $env:COPILOT_SESSION_LOGGER_OTLP_ENABLED) {
    $env:COPILOT_SESSION_LOGGER_OTLP_ENABLED = 'true'
}
if (-not $env:COPILOT_SESSION_LOGGER_OTLP_ENDPOINT) {
    $env:COPILOT_SESSION_LOGGER_OTLP_ENDPOINT = 'http://localhost:4318'
}

$stdinPayload = [Console]::In.ReadToEnd()

if ([string]::IsNullOrWhiteSpace($stdinPayload)) {
    & $bashPath $scriptPath '--event' $Event
} else {
    $stdinPayload | & $bashPath $scriptPath '--event' $Event
}

exit $LASTEXITCODE
