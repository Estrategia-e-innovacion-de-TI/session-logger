#Requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [string]$Event
)

$ErrorActionPreference = 'Stop'

function Get-EnvOrDefault {
    param([string]$Name, [string]$Default)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

function Get-EnvBool {
    param([string]$Name, [bool]$Default = $false)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    switch ($value.ToLowerInvariant()) {
        '1' { return $true }
        'true' { return $true }
        'yes' { return $true }
        'on' { return $true }
        default { return $false }
    }
}

function New-CompactId {
    param([string]$Prefix)
    return "$Prefix$(([guid]::NewGuid().ToString()).ToLowerInvariant())"
}

function Get-NowIso {
    return [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
}

function Read-StdinPayload {
    if (-not [Console]::IsInputRedirected) { return @{} }
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { return @{} }
    try {
        return ConvertFrom-Json -InputObject $raw -Depth 50 -AsHashtable
    }
    catch {
        return @{ _raw_stdin = $raw }
    }
}

function Get-ValueByPath {
    param($Object, [string[]]$Path)
    $current = $Object
    foreach ($segment in $Path) {
        if ($null -eq $current) { return $null }
        if ($current -is [hashtable]) {
            if (-not $current.ContainsKey($segment)) { return $null }
            $current = $current[$segment]
        }
        elseif ($current -is [System.Collections.IDictionary]) {
            if (-not $current.Contains($segment)) { return $null }
            $current = $current[$segment]
        }
        else {
            return $null
        }
    }
    return $current
}

function Get-First {
    param($Object, [object[]]$Paths)
    foreach ($path in $Paths) {
        $value = Get-ValueByPath -Object $Object -Path $path
        if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
            return $value
        }
    }
    return $null
}

function Normalize-EventType {
    param([string]$EventType)
    switch ($EventType) {
        'sessionStart' { return 'session_start' }
        'userPromptSubmitted' { return 'user_prompt' }
        'preToolUse' { return 'tool_use' }
        'postToolUse' { return 'tool_result' }
        'sessionEnd' { return 'session_end' }
        'errorOccurred' { return 'error' }
        default {
            return (($EventType -replace '[^a-zA-Z0-9]+', '_').Trim('_').ToLowerInvariant())
        }
    }
}

function Parse-Jsonish {
    param($Value)
    if ($Value -is [string]) {
        try {
            return ConvertFrom-Json -InputObject $Value -Depth 50 -AsHashtable
        }
        catch {
            return $Value
        }
    }
    return $Value
}

function To-StringArray {
    param($Value)
    if ($null -eq $Value) { return @() }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        $output = @()
        foreach ($item in $Value) {
            if ($null -ne $item -and -not [string]::IsNullOrWhiteSpace([string]$item)) {
                $output += [string]$item
            }
        }
        return $output
    }
    if (-not [string]::IsNullOrWhiteSpace([string]$Value)) {
        return @([string]$Value)
    }
    return @()
}

function Get-ToolPaths {
    param($ToolValue)
    $parsed = Parse-Jsonish -Value $ToolValue
    if (-not ($parsed -is [hashtable])) { return @() }

    $candidates = @(
        'filePath','file_path','path','paths','files','filePaths',
        'attachments','attachment_files','input_files','context_files',
        'images','imagePaths','image_path'
    )

    $out = @()
    foreach ($key in $candidates) {
        if ($parsed.ContainsKey($key)) {
            $out += To-StringArray -Value $parsed[$key]
        }
    }
    return $out
}

function Get-FilesAdded {
    param($Payload)

    $explicit = Get-First -Object $Payload -Paths @(
        @('files_added'), @('added_files'), @('new_files'), @('created_files'),
        @('filesAdded'), @('addedFiles'), @('newFiles'), @('createdFiles'),
        @('attachments'), @('attached_files'), @('attachment_files'),
        @('payload','files_added'), @('payload','added_files'), @('payload','filesAdded'),
        @('payload','addedFiles'), @('payload','attachments'), @('payload','attached_files'), @('payload','attachment_files'),
        @('toolResult','files_added'), @('toolResult','added_files'), @('toolResult','filesAdded'), @('toolResult','addedFiles')
    )

    $toolArgs = Get-First -Object $Payload -Paths @(@('toolArgs'), @('tool_args'), @('tool_input'), @('payload','toolArgs'), @('payload','tool_input'), @('request','toolArgs'))
    $toolResult = Get-First -Object $Payload -Paths @(@('toolResult'), @('tool_result'), @('payload','toolResult'))

    $all = @()
    $all += To-StringArray -Value $explicit
    $all += Get-ToolPaths -ToolValue $toolArgs
    $all += Get-ToolPaths -ToolValue $toolResult

    return @($all | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
}

function Test-ContainsSkillMarker {
    param($Value)

    if ($null -eq $Value) { return $false }
    if ($Value -is [string]) {
        return ([regex]::IsMatch($Value, '(^|[\\/])\.github([\\/])skills([\\/])|#prompt:SKILL\.md|prompt:SKILL\.md|\bskills?\b', 'IgnoreCase'))
    }
    if ($Value -is [hashtable] -or $Value -is [System.Collections.IDictionary]) {
        foreach ($entry in $Value.GetEnumerator()) {
            if (Test-ContainsSkillMarker -Value ([string]$entry.Key)) { return $true }
            if (Test-ContainsSkillMarker -Value $entry.Value) { return $true }
        }
        return $false
    }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($item in $Value) {
            if (Test-ContainsSkillMarker -Value $item) { return $true }
        }
        return $false
    }
    return $false
}

function Get-SkillNameFromValue {
    param($Value)

    if ($null -eq $Value) { return $null }
    if ($Value -is [string]) {
        $match = [regex]::Match($Value, '(?i)(?:^|[\\/])\.github[\\/]skills[\\/](?<name>[^\\/]+)[\\/]')
        if ($match.Success) {
            return $match.Groups['name'].Value
        }
        return $null
    }
    if ($Value -is [hashtable] -or $Value -is [System.Collections.IDictionary]) {
        foreach ($entry in $Value.GetEnumerator()) {
            $fromValue = Get-SkillNameFromValue -Value $entry.Value
            if (-not [string]::IsNullOrWhiteSpace([string]$fromValue)) {
                return $fromValue
            }
            $fromKey = Get-SkillNameFromValue -Value ([string]$entry.Key)
            if (-not [string]::IsNullOrWhiteSpace([string]$fromKey)) {
                return $fromKey
            }
        }
        return $null
    }
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($item in $Value) {
            $name = Get-SkillNameFromValue -Value $item
            if (-not [string]::IsNullOrWhiteSpace([string]$name)) {
                return $name
            }
        }
        return $null
    }
    return $null
}

function Send-ToLoki {
    param($EventObj, [string]$Endpoint, [string]$TenantId, [int]$TimeoutSeconds, [string]$Source)

    $hostnameLabel = $env:COMPUTERNAME
    if ([string]::IsNullOrWhiteSpace($hostnameLabel)) {
        try {
            $hostnameLabel = [System.Net.Dns]::GetHostName()
        }
        catch {
            $hostnameLabel = $null
        }
    }
    if ([string]::IsNullOrWhiteSpace($hostnameLabel)) {
        $hostnameLabel = 'unknown'
    }

    $nowNs = [int64](([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) * 1000000)
    $payload = @{
        streams = @(
            @{
                stream = @{
                    job = 'session-logger-windows'
                    service_name = 'session-logger'
                    hostname = $hostnameLabel
                    source = $Source
                    event_type = if ($null -eq $EventObj.event_type) { 'unknown' } else { $EventObj.event_type }
                    session_id = if ($null -eq $EventObj.session_id) { 'unknown' } else { $EventObj.session_id }
                    repository = if ($null -eq $EventObj.repository) { 'unknown' } else { $EventObj.repository }
                    branch = if ($null -eq $EventObj.branch) { 'unknown' } else { $EventObj.branch }
                    actor = if ($null -eq $EventObj.actor) { 'unknown' } else { $EventObj.actor }
                    files_added_count = ([string](@($EventObj.files_added).Count))
                }
                values = @(@([string]$nowNs, (ConvertTo-Json -InputObject $EventObj -Depth 20 -Compress)))
            }
        )
    }

    $headers = @{ 'Content-Type' = 'application/json' }
    if (-not [string]::IsNullOrWhiteSpace($TenantId)) {
        $headers['X-Scope-OrgID'] = $TenantId
    }

    $body = ConvertTo-Json -InputObject $payload -Depth 20 -Compress
    try {
        $response = Invoke-WebRequest -Uri $Endpoint -Method Post -Body $body -Headers $headers -TimeoutSec $TimeoutSeconds -ErrorAction Stop
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
    }
    catch {
        Write-Warning "loki_send_failed: $($_.Exception.Message)"
        return $false
    }
}

function Send-ToOtlp {
    param($EventObj, [string]$Endpoint, [int]$TimeoutSeconds)

    $base = $Endpoint.TrimEnd('/')
    $nowNs = [int64](([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) * 1000000)
    $traceId = (([guid]::NewGuid().ToString() -replace '-', '').Substring(0, 32)).ToLowerInvariant()
    $spanId = (([guid]::NewGuid().ToString() -replace '-', '').Substring(0, 16)).ToLowerInvariant()

    $sessionId = if ($null -eq $EventObj.session_id) { 'unknown' } else { $EventObj.session_id }
    $eventId = if ($null -eq $EventObj.event_id) { 'unknown' } else { $EventObj.event_id }
    $eventType = if ($null -eq $EventObj.event_type) { 'session_logger_event' } else { $EventObj.event_type }
    $repository = if ($null -eq $EventObj.repository) { 'unknown' } else { $EventObj.repository }
    $branch = if ($null -eq $EventObj.branch) { 'unknown' } else { $EventObj.branch }

    $tracePayload = @{
        resourceSpans = @(
            @{
                resource = @{
                    attributes = @(
                        @{ key = 'service.name'; value = @{ stringValue = 'session-logger' } },
                        @{ key = 'service.namespace'; value = @{ stringValue = 'marvin' } },
                        @{ key = 'service.instance.id'; value = @{ stringValue = "$sessionId`:$eventId" } }
                    )
                }
                scopeSpans = @(
                    @{
                        scope = @{ name = 'session-logger-windows'; version = '0.2.0-windows' }
                        spans = @(
                            @{
                                traceId = $traceId
                                spanId = $spanId
                                name = $eventType
                                kind = 1
                                startTimeUnixNano = [string]$nowNs
                                endTimeUnixNano = [string]($nowNs + 1000)
                                status = @{ code = 1 }
                            }
                        )
                    }
                )
            }
        )
    }

    $metricPayload = @{
        resourceMetrics = @(
            @{
                resource = @{ attributes = @(@{ key = 'service.name'; value = @{ stringValue = 'session-logger' } }) }
                scopeMetrics = @(
                    @{
                        scope = @{ name = 'session-logger-windows'; version = '0.2.0-windows' }
                        metrics = @(
                            @{
                                name = 'session_logger_events_total'
                                description = 'Events captured by session-logger Windows hook'
                                unit = '1'
                                sum = @{
                                    aggregationTemporality = 2
                                    isMonotonic = $true
                                    dataPoints = @(
                                        @{
                                            timeUnixNano = [string]$nowNs
                                            asInt = '1'
                                            attributes = @(
                                                @{ key = 'event_type'; value = @{ stringValue = $eventType } },
                                                @{ key = 'repository'; value = @{ stringValue = $repository } },
                                                @{ key = 'branch'; value = @{ stringValue = $branch } }
                                            )
                                        }
                                    )
                                }
                            }
                        )
                    }
                )
            }
        )
    }

    $headers = @{ 'Content-Type' = 'application/json' }
    try {
        $traceBody = ConvertTo-Json -InputObject $tracePayload -Depth 20 -Compress
        $metricBody = ConvertTo-Json -InputObject $metricPayload -Depth 20 -Compress
        $traceRes = Invoke-WebRequest -Uri "$base/v1/traces" -Method Post -Body $traceBody -Headers $headers -TimeoutSec $TimeoutSeconds -ErrorAction Stop
        $metricRes = Invoke-WebRequest -Uri "$base/v1/metrics" -Method Post -Body $metricBody -Headers $headers -TimeoutSec $TimeoutSeconds -ErrorAction Stop
        return ($traceRes.StatusCode -ge 200 -and $traceRes.StatusCode -lt 300 -and $metricRes.StatusCode -ge 200 -and $metricRes.StatusCode -lt 300)
    }
    catch {
        Write-Warning "otlp_send_failed: $($_.Exception.Message)"
        return $false
    }
}

function Main {
    $loggerSource = Get-EnvOrDefault -Name 'COPILOT_SESSION_LOGGER_SOURCE' -Default 'github_copilot_hook'
    $rawLokiEnabled = [Environment]::GetEnvironmentVariable('COPILOT_SESSION_LOGGER_LOKI_ENABLED')
    $rawLokiEndpoint = [Environment]::GetEnvironmentVariable('COPILOT_SESSION_LOGGER_LOKI_ENDPOINT')
    $rawLokiTenantId = [Environment]::GetEnvironmentVariable('COPILOT_SESSION_LOGGER_LOKI_TENANT_ID')
    if ([string]::IsNullOrWhiteSpace($rawLokiEnabled)) {
        $lokiEnabled = (-not [string]::IsNullOrWhiteSpace($rawLokiEndpoint)) -or (-not [string]::IsNullOrWhiteSpace($rawLokiTenantId))
    }
    else {
        $lokiEnabled = Get-EnvBool -Name 'COPILOT_SESSION_LOGGER_LOKI_ENABLED' -Default $false
    }
    $lokiEndpoint = Get-EnvOrDefault -Name 'COPILOT_SESSION_LOGGER_LOKI_ENDPOINT' -Default 'http://localhost:3100/loki/api/v1/push'
    $lokiTenantId = Get-EnvOrDefault -Name 'COPILOT_SESSION_LOGGER_LOKI_TENANT_ID' -Default ''
    $rawOtlpEnabled = [Environment]::GetEnvironmentVariable('COPILOT_SESSION_LOGGER_OTLP_ENABLED')
    $rawOtlpEndpoint = [Environment]::GetEnvironmentVariable('COPILOT_SESSION_LOGGER_OTLP_ENDPOINT')
    if ([string]::IsNullOrWhiteSpace($rawOtlpEnabled)) {
        $otlpEnabled = -not [string]::IsNullOrWhiteSpace($rawOtlpEndpoint)
    }
    else {
        $otlpEnabled = Get-EnvBool -Name 'COPILOT_SESSION_LOGGER_OTLP_ENABLED' -Default $false
    }
    $otlpEndpoint = Get-EnvOrDefault -Name 'COPILOT_SESSION_LOGGER_OTLP_ENDPOINT' -Default 'http://localhost:4318'
    $timeoutSeconds = [int](Get-EnvOrDefault -Name 'COPILOT_SESSION_LOGGER_TIMEOUT_SECONDS' -Default '2')
    $actor = Get-EnvOrDefault -Name 'COPILOT_SESSION_LOGGER_ACTOR' -Default $env:USERNAME

    $payload = Read-StdinPayload
    $sessionId = (Get-First -Object $payload -Paths @(@('session_id'), @('sessionId'), @('invocation','sessionId'), @('payload','sessionId')))
    if ([string]::IsNullOrWhiteSpace([string]$sessionId)) {
        $sessionId = New-CompactId -Prefix 'sess_'
    }

    $eventType = Normalize-EventType -EventType $Event
    $toolNameRaw = Get-First -Object $payload -Paths @(@('tool_name'), @('toolName'), @('tool'), @('payload','toolName'))
    $toolNameText = if ([string]::IsNullOrWhiteSpace([string]$toolNameRaw)) { $null } else { [string]$toolNameRaw }
    $toolName = if ([string]::IsNullOrWhiteSpace([string]$toolNameText)) { $null } else { $toolNameText.ToLowerInvariant() }
    $toolNameCanonicalRaw = if ([string]::IsNullOrWhiteSpace([string]$toolNameText)) { $null } else { ($toolNameText -replace '^[^.]+\.', '') }
    $toolNameCanonical = if ([string]::IsNullOrWhiteSpace([string]$toolNameCanonicalRaw)) { $null } else { $toolNameCanonicalRaw.ToLowerInvariant() }
    $agentName = Get-First -Object $payload -Paths @(@('agent_name'), @('agentName'), @('payload','agent_name'), @('payload','agentName'), @('request','agent_name'), @('request','agentName'))
    $modeRaw = Get-First -Object $payload -Paths @(@('mode'), @('chat_mode'), @('chatMode'), @('copilot_mode'), @('copilotMode'), @('invocation','mode'), @('payload','mode'), @('payload','chat_mode'), @('payload','chatMode'), @('request','mode'), @('request','chat_mode'), @('request','chatMode'))
    $mode = if ([string]::IsNullOrWhiteSpace([string]$modeRaw)) { $null } else { (([string]$modeRaw) -replace '[^a-zA-Z0-9]+', '_').Trim('_').ToLowerInvariant() }
    $filePathCandidate = Get-First -Object $payload -Paths @(@('filePath'), @('file_path'), @('payload','filePath'), @('payload','file_path'), @('request','filePath'), @('request','file_path'))
    $skillDetected = (Test-ContainsSkillMarker -Value $filePathCandidate)
    if (-not $skillDetected) {
        $skillDetected = Test-ContainsSkillMarker -Value @(
            $payload.prompt, $payload.userPrompt, $payload.message, $payload.input, $payload.text, $payload.initialPrompt,
            (Get-ValueByPath -Object $payload -Path @('request','prompt')),
            (Get-ValueByPath -Object $payload -Path @('payload','prompt')),
            $payload.attachments,
            (Get-ValueByPath -Object $payload -Path @('payload','attachments')),
            (Get-ValueByPath -Object $payload -Path @('request','attachments')),
            $payload.toolArgs, $payload.tool_args, $payload.tool_input,
            $payload.toolResult, $payload.tool_result,
            (Get-ValueByPath -Object $payload -Path @('payload','toolArgs')),
            (Get-ValueByPath -Object $payload -Path @('payload','toolResult'))
        )
    }
    $pluginDetected = ($null -ne $toolNameCanonical -and $toolNameCanonical -match '^(vscode_|extension_|plugin_|plugin\.|copilot\.)')
    $skillName = Get-SkillNameFromValue -Value @(
        $filePathCandidate,
        $payload.attachments,
        (Get-ValueByPath -Object $payload -Path @('payload','attachments')),
        (Get-ValueByPath -Object $payload -Path @('request','attachments')),
        $payload.prompt,
        (Get-ValueByPath -Object $payload -Path @('payload','prompt')),
        (Get-ValueByPath -Object $payload -Path @('request','prompt')),
        $payload.toolArgs,
        $payload.tool_args,
        $payload.tool_input,
        (Get-ValueByPath -Object $payload -Path @('payload','toolArgs'))
    )
    $invocationOrigin = if ($null -ne $toolNameCanonical -and $toolNameCanonical -match '^mcp_') {
        'mcp'
    }
    elseif ($skillDetected) {
        'skill'
    }
    elseif ($pluginDetected) {
        'plugin'
    }
    elseif ($toolNameCanonical -eq 'runsubagent' -or -not [string]::IsNullOrWhiteSpace([string]$agentName) -or $mode -eq 'agent') {
        'custom_agent'
    }
    else {
        'standard_tool'
    }
    $invocationName = if ($invocationOrigin -eq 'skill') {
        if (-not [string]::IsNullOrWhiteSpace([string]$skillName)) { $skillName }
        elseif (-not [string]::IsNullOrWhiteSpace([string]$agentName)) { [string]$agentName }
        else { [string]$toolNameRaw }
    }
    elseif ($invocationOrigin -eq 'custom_agent') {
        if (-not [string]::IsNullOrWhiteSpace([string]$agentName)) { [string]$agentName }
        else { [string]$toolNameRaw }
    }
    elseif ($invocationOrigin -eq 'mcp' -or $invocationOrigin -eq 'plugin') {
        if (-not [string]::IsNullOrWhiteSpace([string]$toolNameCanonicalRaw)) { [string]$toolNameCanonicalRaw } else { [string]$toolNameRaw }
    }
    else {
        $null
    }

    $eventObj = [ordered]@{
        event_id = (New-CompactId -Prefix 'evt_')
        session_id = $sessionId
        timestamp = Get-NowIso
        event_type = $eventType
        userPrompt_id = if ($eventType -eq 'user_prompt') { New-CompactId -Prefix 'up_' } else { $null }
        parent_userPrompt_id = $null
        actor = $actor
        user_id = $actor
        source = $loggerSource
        repository = (Get-First -Object $payload -Paths @(@('repository'), @('repo_name'), @('payload','repository')))
        branch = (Get-First -Object $payload -Paths @(@('branch'), @('git_branch'), @('payload','branch')))
        workspace = (Get-First -Object $payload -Paths @(@('workspace'), @('cwd'), @('workingDirectory'), @('working_directory'), @('payload','cwd')))
        tool_name = $toolNameRaw
        mode = $mode
        invocation_origin = $invocationOrigin
        invocation_name = $invocationName
        files_added = @(Get-FilesAdded -Payload $payload)
        metadata = @{
            hook_event_type = $Event
            logger_version = '0.2.0-windows'
            mode = $mode
            invocation_origin = $invocationOrigin
            invocation_name = $invocationName
            skill_name = if ($invocationOrigin -eq 'skill') { $invocationName } else { $null }
            custom_agent_name = if ($invocationOrigin -eq 'custom_agent') { $invocationName } else { $null }
            mcp_name = if ($invocationOrigin -eq 'mcp') { $invocationName } else { $null }
            plugin_name = if ($invocationOrigin -eq 'plugin') { $invocationName } else { $null }
            is_mcp = ($invocationOrigin -eq 'mcp')
            is_skill = ($invocationOrigin -eq 'skill')
            is_plugin = ($invocationOrigin -eq 'plugin')
            is_custom_agent = ($invocationOrigin -eq 'custom_agent')
        }
        raw_payload = $payload
        created_at = Get-NowIso
    }

    $attempted = 0
    $success = 0
    if ($lokiEnabled) {
        $attempted++
        if (Send-ToLoki -EventObj $eventObj -Endpoint $lokiEndpoint -TenantId $lokiTenantId -TimeoutSeconds $timeoutSeconds -Source $loggerSource) {
            $success++
        }
    }
    if ($otlpEnabled) {
        $attempted++
        if (Send-ToOtlp -EventObj $eventObj -Endpoint $otlpEndpoint -TimeoutSeconds $timeoutSeconds) {
            $success++
        }
    }

    if ($attempted -eq 0) {
        Write-Error 'no_observability_transports_enabled: enable COPILOT_SESSION_LOGGER_LOKI_ENABLED and/or COPILOT_SESSION_LOGGER_OTLP_ENABLED'
        exit 1
    }
    if ($success -ne $attempted) {
        Write-Error 'one_or_more_observability_transports_failed'
        exit 1
    }

    ConvertTo-Json -InputObject $eventObj -Depth 20 -Compress
    exit 0
}

Main
