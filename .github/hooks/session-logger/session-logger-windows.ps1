#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$Event
)

$ErrorActionPreference = 'Stop'

# Configuration
$LoggerVersion = "0.2.0-windows"
$LoggerSource = $env:COPILOT_SESSION_LOGGER_SOURCE -or "github_copilot_hook"
$LoggerHome = $env:COPILOT_SESSION_LOGGER_HOME -or (Join-Path $env:USERPROFILE ".session-logger")
$LoggerLogsDir = $env:COPILOT_SESSION_LOGGER_LOGS_DIR -or (Join-Path $LoggerHome "logs")
$LoggerStateDir = $env:COPILOT_SESSION_LOGGER_STATE_DIR -or (Join-Path $LoggerHome "state")
$LoggerQueueDir = $env:COPILOT_SESSION_LOGGER_QUEUE_DIR -or (Join-Path $LoggerHome "queue")
$HttpEnabled = [System.Convert]::ToBoolean(($env:COPILOT_SESSION_LOGGER_HTTP_ENABLED -eq "true"))
$HttpEndpoint = $env:COPILOT_SESSION_LOGGER_ENDPOINT
$HttpApiKey = $env:COPILOT_SESSION_LOGGER_API_KEY
$LokiEnabled = [System.Convert]::ToBoolean(($env:COPILOT_SESSION_LOGGER_LOKI_ENABLED -eq "true"))
$LokiEndpoint = $env:COPILOT_SESSION_LOGGER_LOKI_ENDPOINT -or "http://localhost:3100/loki/api/v1/push"
$LokiTenantId = $env:COPILOT_SESSION_LOGGER_LOKI_TENANT_ID
$OtlpEnabled = [System.Convert]::ToBoolean(($env:COPILOT_SESSION_LOGGER_OTLP_ENABLED -eq "true"))
$OtlpEndpoint = $env:COPILOT_SESSION_LOGGER_OTLP_ENDPOINT -or "http://localhost:4318"
$TimeoutSeconds = [int]($env:COPILOT_SESSION_LOGGER_TIMEOUT_SECONDS -or 2)
$RedactSecrets = [System.Convert]::ToBoolean(($env:COPILOT_SESSION_LOGGER_REDACT_SECRETS -ne "false"))
$OfflineQueueEnabled = [System.Convert]::ToBoolean(($env:COPILOT_SESSION_LOGGER_OFFLINE_QUEUE_ENABLED -ne "false"))
$Actor = $env:COPILOT_SESSION_LOGGER_ACTOR -or $env:USERNAME -or "unknown"
$CopilotUser = $env:COPILOT_SESSION_LOGGER_COPILOT_USER
$MetadataJson = $env:COPILOT_SESSION_LOGGER_METADATA_JSON -or "{}"

function New-Guid-Short {
    "$(Get-Random -Minimum 100000 -Maximum 999999)_$(Get-Date -Format 'yyyyMMddHHmmss')_$(Get-Random -Minimum 1000 -Maximum 9999)"
}

function Get-Now-Iso8601 {
    [System.DateTime]::UtcNow.ToString("o")
}

function Read-StdinPayload {
    $input = ""
    if (-not [System.Console]::IsInputRedirected) {
        return @{}
    }
    $input = [System.Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($input)) {
        return @{}
    }
    try {
        return ConvertFrom-Json -InputObject $input -ErrorAction Stop
    }
    catch {
        return @{ _raw_stdin = $input }
    }
}

function Normalize-EventType {
    param([string]$EventType)
    $map = @{
        "sessionStart" = "session_start"
        "userPromptSubmitted" = "user_prompt"
        "preToolUse" = "tool_use"
        "postToolUse" = "tool_result"
        "sessionEnd" = "session_end"
        "errorOccurred" = "error"
    }
    if ($map.ContainsKey($EventType)) {
        return $map[$EventType]
    }
    return ($EventType -replace '[^a-z0-9]', '_').ToLower()
}

function Extract-Field {
    param($Payload, [string[]]$Paths, $Default = $null)
    foreach ($path in $Paths) {
        $value = $Payload
        foreach ($segment in $path -split "\.") {
            if ($null -eq $value) { break }
            if ($value -is [hashtable]) {
                $value = $value[$segment]
            }
            elseif ($value -is [PSCustomObject]) {
                $value = $value.$segment
            }
            else {
                $value = $null
                break
            }
        }
        if ($null -ne $value -and $value -ne "") {
            return $value
        }
    }
    return $Default
}

function Remove-DuplicateExtractedKeys {
    param($Object)
    
    if ($Object -is [hashtable]) {
        $keysToRemove = @()
        foreach ($key in $Object.Keys) {
            if ($key -match "_extracted$") {
                $baseKey = $key -replace "_extracted$", ""
                if ($Object.ContainsKey($baseKey) -and $Object[$baseKey] -eq $Object[$key]) {
                    $keysToRemove += $key
                }
            }
        }
        foreach ($key in $keysToRemove) {
            $Object.Remove($key)
        }
        
        # Recursively process nested objects and arrays
        foreach ($key in $Object.Keys) {
            if ($Object[$key] -is [hashtable]) {
                Remove-DuplicateExtractedKeys -Object $Object[$key]
            }
            elseif ($Object[$key] -is [PSCustomObject]) {
                Remove-DuplicateExtractedKeys -Object ([hashtable]$Object[$key])
            }
            elseif ($Object[$key] -is [array]) {
                foreach ($item in $Object[$key]) {
                    if ($item -is [hashtable]) {
                        Remove-DuplicateExtractedKeys -Object $item
                    }
                }
            }
        }
    }
    elseif ($Object -is [PSCustomObject]) {
        $hashtable = @{}
        $Object.PSObject.Properties | ForEach-Object { $hashtable[$_.Name] = $_.Value }
        Remove-DuplicateExtractedKeys -Object $hashtable
        return $hashtable
    }
    
    return $Object
}

function Redact-Secrets {
    param($Payload)
    if (-not $RedactSecrets) {
        Remove-DuplicateExtractedKeys -Object $Payload
        return $Payload
    }
    
    $sensitivePatterns = @(
        @{ Pattern = "github_pat_[A-Za-z0-9_]{20,}"; Replacement = "[REDACTED:GITHUB_TOKEN]" }
        @{ Pattern = "ghp_[A-Za-z0-9_]{20,}"; Replacement = "[REDACTED:GITHUB_TOKEN]" }
        @{ Pattern = "sk-[A-Za-z0-9_-]{20,}"; Replacement = "[REDACTED:OPENAI_KEY]" }
        @{ Pattern = "AKIA[0-9A-Z]{16}"; Replacement = "[REDACTED:AWS_KEY]" }
    )
    
    $json = ConvertTo-Json -InputObject $Payload -Depth 10
    foreach ($item in $sensitivePatterns) {
        $json = $json -replace $item.Pattern, $item.Replacement
    }
    
    $sanitized = ConvertFrom-Json -InputObject $json -ErrorAction SilentlyContinue
    Remove-DuplicateExtractedKeys -Object $sanitized
    
    return $sanitized
}

function Build-NormalizedEvent {
    param(
        $Payload,
        [string]$HookEventType,
        [string]$EventId,
        [string]$SessionId,
        [string]$UserPromptId,
        [string]$ParentUserPromptId,
        [string]$Actor
    )
    
    $now = Get-Now-Iso8601
    $normalizedEventType = Normalize-EventType -EventType $HookEventType
    $sanitizedPayload = Redact-Secrets -Payload $Payload
    
    $event = @{
        event_id = $EventId
        session_id = $SessionId
        timestamp = $now
        event_type = $normalizedEventType
        userPrompt_id = if ([string]::IsNullOrEmpty($UserPromptId)) { $null } else { $UserPromptId }
        parent_userPrompt_id = if ([string]::IsNullOrEmpty($ParentUserPromptId)) { $null } else { $ParentUserPromptId }
        actor = if ([string]::IsNullOrEmpty($Actor)) { $null } else { $Actor }
        user_id = if ([string]::IsNullOrEmpty($Actor)) { $null } else { $Actor }
        source = $LoggerSource
        repository = Extract-Field -Payload $sanitizedPayload -Paths @("repository", "repo_name", "payload.repository")
        branch = Extract-Field -Payload $sanitizedPayload -Paths @("branch", "git_branch", "payload.branch")
        workspace = Extract-Field -Payload $sanitizedPayload -Paths @("workspace", "cwd", "payload.cwd") -Default $PWD
        tool_name = Extract-Field -Payload $sanitizedPayload -Paths @("tool_name", "toolName", "tool", "payload.toolName")
        tool_input_summary = Extract-Field -Payload $sanitizedPayload -Paths @("tool_input_summary", "toolInputSummary")
        tool_result_summary = Extract-Field -Payload $sanitizedPayload -Paths @("tool_result_summary", "toolResultSummary")
        prompt_text = Extract-Field -Payload $sanitizedPayload -Paths @("prompt", "userPrompt", "message", "input", "text", "payload.prompt")
        assistant_response_summary = Extract-Field -Payload $sanitizedPayload -Paths @("assistant_response", "response", "payload.assistant_response")
        files_touched = @(Extract-Field -Payload $sanitizedPayload -Paths @("files_touched", "files", "payload.files_touched") -Default @())
        commands_executed = @(Extract-Field -Payload $sanitizedPayload -Paths @("commands_executed", "commands", "payload.commands_executed") -Default @())
        status = Extract-Field -Payload $sanitizedPayload -Paths @("status", "reason", "payload.status")
        duration_ms = if ($null -ne (Extract-Field -Payload $sanitizedPayload -Paths @("duration_ms", "durationMs"))) {
            [int](Extract-Field -Payload $sanitizedPayload -Paths @("duration_ms", "durationMs"))
        }
        else {
            $null
        }
        metadata = @{
            hook_event_type = $HookEventType
            logger_version = $LoggerVersion
            copilot_user = if ([string]::IsNullOrEmpty($CopilotUser)) { $null } else { $CopilotUser }
        }
        raw_payload = $sanitizedPayload
        created_at = $now
    }
    
    return $event
}

function Write-Jsonl-Event {
    param($Event)
    $dateDir = $Event.timestamp.Substring(0, 10)
    $logsPath = Join-Path $LoggerLogsDir $dateDir
    $outputFile = Join-Path $logsPath "events.jsonl"
    
    if (-not (Test-Path $logsPath)) {
        New-Item -ItemType Directory -Path $logsPath -Force | Out-Null
    }
    
    $json = ConvertTo-Json -InputObject $Event -Depth 10 -Compress
    Add-Content -Path $outputFile -Value $json -Encoding UTF8
    return $outputFile
}

function Send-ToHttp {
    param($Event)
    if (-not $HttpEnabled -or [string]::IsNullOrEmpty($HttpEndpoint) -or [string]::IsNullOrEmpty($HttpApiKey)) {
        return $false
    }
    
    try {
        $body = ConvertTo-Json -InputObject $Event -Depth 10 -Compress
        $headers = @{
            "Content-Type" = "application/json"
            "Authorization" = "Bearer $HttpApiKey"
            "X-Logger-Token" = $HttpApiKey
            "X-Logger-Version" = $LoggerVersion
        }
        
        $response = Invoke-WebRequest -Uri $HttpEndpoint -Method Post -Body $body -Headers $headers `
            -TimeoutSec $TimeoutSeconds -ErrorAction SilentlyContinue
        
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    }
    catch {
        Write-Warning "HTTP send failed: $_"
        return $false
    }
}

function Send-ToLoki {
    param($Event)
    if (-not $LokiEnabled -or [string]::IsNullOrEmpty($LokiEndpoint)) {
        return $false
    }
    
    try {
        $now = [int64]((Get-Date).ToUniversalTime().Ticks - 621355968000000000) * 100
        $payload = @{
            streams = @(
                @{
                    stream = @{
                        job = "session-logger-windows"
                        service_name = "session-logger"
                        source = $LoggerSource
                        event_type = $Event.event_type
                        session_id = $Event.session_id
                        repository = $Event.repository
                        actor = $Event.actor
                    }
                    values = @(@($now, (ConvertTo-Json -InputObject $Event -Depth 10 -Compress)))
                }
            )
        }
        
        $body = ConvertTo-Json -InputObject $payload -Depth 10 -Compress
        $headers = @{ "Content-Type" = "application/json" }
        if (-not [string]::IsNullOrEmpty($LokiTenantId)) {
            $headers["X-Scope-OrgID"] = $LokiTenantId
        }
        
        $response = Invoke-WebRequest -Uri $LokiEndpoint -Method Post -Body $body -Headers $headers `
            -TimeoutSec $TimeoutSeconds -ErrorAction SilentlyContinue
        
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    }
    catch {
        Write-Warning "Loki send failed: $_"
        return $false
    }
}

function Send-ToOtlp {
    param($Event)
    if (-not $OtlpEnabled -or [string]::IsNullOrEmpty($OtlpEndpoint)) {
        return $false
    }
    
    try {
        $now = [int64]((Get-Date).ToUniversalTime().Ticks - 621355968000000000) * 100000
        $traceId = (([guid]::NewGuid().ToString() -replace '-', '').Substring(0, 32)).ToLower()
        $spanId = (([guid]::NewGuid().ToString() -replace '-', '').Substring(0, 16)).ToLower()
        
        $payload = @{
            resourceSpans = @(
                @{
                    resource = @{
                        attributes = @(
                            @{ key = "service.name"; value = @{ stringValue = "session-logger" } }
                            @{ key = "service.namespace"; value = @{ stringValue = "marvin" } }
                            @{ key = "service.instance.id"; value = @{ stringValue = "$($Event.session_id):$($Event.event_id)" } }
                        )
                    }
                    scopeSpans = @(
                        @{
                            scope = @{ name = "session-logger-windows"; version = $LoggerVersion }
                            spans = @(
                                @{
                                    traceId = $traceId
                                    spanId = $spanId
                                    name = $Event.event_type
                                    kind = 1
                                    startTimeUnixNano = "$now"
                                    endTimeUnixNano = "$($now + 1000)"
                                    status = @{ code = 1 }
                                }
                            )
                        }
                    )
                }
            )
        }
        
        $body = ConvertTo-Json -InputObject $payload -Depth 10 -Compress
        $headers = @{ "Content-Type" = "application/json" }
        
        $response = Invoke-WebRequest -Uri "$OtlpEndpoint/v1/traces" -Method Post -Body $body -Headers $headers `
            -TimeoutSec $TimeoutSeconds -ErrorAction SilentlyContinue
        
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    }
    catch {
        Write-Warning "OTLP send failed: $_"
        return $false
    }
}

function Main {
    try {
        # Ensure directories exist
        foreach ($dir in @($LoggerLogsDir, $LoggerStateDir, $LoggerQueueDir)) {
            if (-not (Test-Path $dir)) {
                New-Item -ItemType Directory -Path $dir -Force | Out-Null
            }
        }
        
        # Read payload
        $payload = Read-StdinPayload
        
        # Generate IDs
        $eventId = "evt_$(New-Guid-Short)"
        $userPromptId = ""
        $sessionId = Extract-Field -Payload $payload -Paths @("session_id", "sessionId", "invocation.sessionId") -Default "sess_$(New-Guid-Short)"
        
        if ($Event -eq "userPromptSubmitted") {
            $userPromptId = "up_$(New-Guid-Short)"
        }
        
        # Build event
        $normalizedEvent = Build-NormalizedEvent `
            -Payload $payload `
            -HookEventType $Event `
            -EventId $eventId `
            -SessionId $sessionId `
            -UserPromptId $userPromptId `
            -ParentUserPromptId "" `
            -Actor $Actor
        
        # Write local JSONL
        Write-Jsonl-Event -Event $normalizedEvent | Out-Null
        
        # Send to destinations
        $sent = 0
        $attempted = 0
        
        if ($HttpEnabled) {
            $attempted++
            if (Send-ToHttp -Event $normalizedEvent) { $sent++ }
        }
        
        if ($LokiEnabled) {
            $attempted++
            if (Send-ToLoki -Event $normalizedEvent) { $sent++ }
        }
        
        if ($OtlpEnabled) {
            $attempted++
            if (Send-ToOtlp -Event $normalizedEvent) { $sent++ }
        }
        
        # Output event in compact JSON format (for stdout/logging)
        ConvertTo-Json -InputObject $normalizedEvent -Depth 10 -Compress
        
        exit 0
    }
    catch {
        Write-Error "session-logger-windows failed: $_"
        exit 1
    }
}

# Run
Main
