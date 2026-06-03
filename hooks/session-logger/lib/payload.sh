#!/usr/bin/env bash
set -euo pipefail

read_stdin_payload() {
  local raw_input
  raw_input="$(cat || true)"
  if [ -z "${raw_input//[[:space:]]/}" ]; then
    jq -cn '{}'
    return 0
  fi
  if printf '%s' "$raw_input" | jq -e . >/dev/null 2>&1; then
    printf '%s' "$raw_input" | jq -c .
    return 0
  fi
  jq -cn --arg raw_stdin "$raw_input" '{_raw_stdin:$raw_stdin}'
}

extract_event_type() {
  local payload="$1"
  local override="${2:-}"
  if [ -n "$override" ]; then
    printf '%s\n' "$override"
    return 0
  fi
  jq -r '
    .event_type // .eventType // .hook_event // .hookEvent // .payload.event_type // empty
  ' <<< "$payload"
}

normalize_event_type() {
  local event_type="$1"
  jq -nr --arg event_type "$event_type" '
    def normalize($event):
      if $event == "sessionStart" then "session_start"
      elif $event == "userPromptSubmitted" then "user_prompt"
      elif $event == "preToolUse" then "tool_use"
      elif $event == "postToolUse" then "tool_result"
      elif $event == "sessionEnd" then "session_end"
      elif $event == "errorOccurred" then "error"
      else ($event | ascii_downcase | gsub("[^a-z0-9]+"; "_") | gsub("^_|_$"; ""))
      end;
    normalize($event_type)
  '
}

extract_session_id() {
  local payload="$1"
  local override="${2:-}"
  if [ -n "$override" ]; then
    printf '%s\n' "$override"
    return 0
  fi
  jq -r '
    .session_id // .sessionId // .invocation.sessionId // .payload.sessionId // empty
  ' <<< "$payload"
}

extract_user_prompt() {
  local payload="$1"
  jq -r '
    .prompt // .userPrompt // .message // .input // .text // .initialPrompt //
    .request.prompt // .payload.prompt // empty
  ' <<< "$payload"
}

extract_existing_userPrompt_id() {
  local payload="$1"
  jq -r '.userPrompt_id // .user_prompt_id // .payload.userPrompt_id // empty' <<< "$payload"
}

extract_existing_parent_userPrompt_id() {
  local payload="$1"
  jq -r '.parent_userPrompt_id // .parent_user_prompt_id // .payload.parent_userPrompt_id // empty' <<< "$payload"
}

extract_actor() {
  local payload="$1"
  jq -r --arg fallback "$SESSION_LOGGER_ACTOR" '
    .actor // .user // .username // .invocation.user // .payload.actor // $fallback // empty
  ' <<< "$payload"
}

extract_copilot_user() {
  local payload="$1"
  jq -r --arg fallback "$SESSION_LOGGER_COPILOT_USER" '
    .copilot_user // .copilotUser // .github_copilot_user // .githubCopilotUser //
    .invocation.copilotUser // .invocation.user // .payload.copilot_user //
    .payload.copilotUser // .payload.user // .user // .username // $fallback // empty
  ' <<< "$payload"
}

extract_working_directory() {
  local payload="$1"
  jq -r --arg pwd "$PWD" '
    .workspace // .cwd // .workingDirectory // .working_directory // .payload.cwd // $pwd
  ' <<< "$payload"
}

extract_tool_metadata() {
  local payload="$1"
  jq -c '
    def parse_json: if type == "string" then (fromjson? // .) else . end;
    def normalize_text:
      if . == null then null
      elif type == "string" then .
      else tostring
      end;
    def has_skill_marker:
      if . == null then false
      elif type == "string" then
        test("(^|/|\\\\)\\.github(/|\\\\)skills(/|\\\\)|#prompt:SKILL\\.md|prompt:SKILL\\.md|\\bskills?\\b"; "i")
      elif type == "array" then any(.[]; has_skill_marker)
      elif type == "object" then any(to_entries[]; (.key | has_skill_marker) or (.value | has_skill_marker))
      else false
      end;
    def first_skill_name:
      if . == null then null
      elif type == "string" then
        (try (capture("(?i)(?:^|[\\\\/])\\.github[\\\\/]skills[\\\\/](?<name>[^\\\\/]+)[\\\\/]").name) catch null)
      elif type == "array" then
        reduce .[] as $item (null; if . != null then . else ($item | first_skill_name) end)
      elif type == "object" then
        reduce to_entries[] as $entry (null; if . != null then . else (($entry.value | first_skill_name) // ($entry.key | first_skill_name)) end)
      else null
      end;
    def sanitize_mode:
      if . == null then null
      elif type == "string" then
        (. | ascii_downcase | gsub("[^a-z0-9]+"; "_") | gsub("^_|_$"; ""))
      else null
      end;
    def summarize:
      if . == null then null
      elif type == "object" then (.summary // .textResultForLlm // .output // .message // .error // tojson)
      elif type == "array" then tojson
      else tostring
      end;
    (.toolArgs // .tool_args // .tool_input // .payload.toolArgs // .payload.tool_input // .request.toolArgs // null | parse_json) as $tool_input |
    (.toolResult // .tool_result // .payload.toolResult // null | parse_json) as $tool_result |
    (.tool_name // .toolName // .tool // .payload.toolName // null) as $tool_name_raw |
    ($tool_name_raw | if . == null then null else tostring end) as $tool_name_text |
    ($tool_name_text | if . == null then null else ascii_downcase end) as $tool_name |
    ($tool_name_text | if . == null then null else (sub("^[^.]+\\."; "")) end) as $tool_name_canonical_raw |
    ($tool_name_canonical_raw | if . == null then null else ascii_downcase end) as $tool_name_canonical |
    (
      .agent_name // .agentName // .payload.agent_name // .payload.agentName //
      .request.agent_name // .request.agentName //
      $tool_input.agent_name // $tool_input.agentName // null
    ) as $agent_name |
    (
      $tool_input.filePath // $tool_input.file_path //
      .filePath // .file_path // .payload.filePath // .payload.file_path //
      .request.filePath // .request.file_path // null
    ) as $file_path |
    (
      ($file_path != null and ($file_path | tostring | has_skill_marker)) or
      ([.prompt, .userPrompt, .message, .input, .text, .initialPrompt, .request.prompt, .payload.prompt, .attachments, .payload.attachments, .request.attachments, .toolArgs, .tool_args, .tool_input, .toolResult, .tool_result, .payload.toolArgs, .payload.toolResult] | has_skill_marker)
    ) as $skill_detected |
    (
      if ($tool_name_canonical != null and ($tool_name_canonical | test("^(vscode_|extension_|plugin_|plugin\\.|copilot\\.)"))) then true
      else false
      end
    ) as $plugin_detected |
    (
      [
        $file_path,
        .filePath, .file_path,
        .payload.filePath, .payload.file_path,
        .request.filePath, .request.file_path,
        .attachments, .payload.attachments, .request.attachments,
        .prompt, .payload.prompt, .request.prompt,
        .toolArgs, .tool_args, .tool_input, .payload.toolArgs
      ] | first_skill_name
    ) as $skill_name |
    (
      if ($tool_name_canonical != null and ($tool_name_canonical | test("^mcp_"))) then "mcp"
      elif $skill_detected then "skill"
      elif $plugin_detected then "plugin"
      elif (
        $tool_name_canonical == "runsubagent" or
        $agent_name != null or
        (
          .mode // .chat_mode // .chatMode // .copilot_mode // .copilotMode //
          .invocation.mode // .payload.mode // .payload.chat_mode // .payload.chatMode //
          .request.mode // .request.chat_mode // .request.chatMode // null
          | sanitize_mode
        ) == "agent"
      ) then "custom_agent"
      else "standard_tool"
      end
    ) as $invocation_origin |
    (
      if $invocation_origin == "skill" then ($skill_name // ($agent_name | normalize_text) // ($tool_name_raw | normalize_text))
      elif $invocation_origin == "custom_agent" then (($agent_name | normalize_text) // ($tool_name_raw | normalize_text))
      elif $invocation_origin == "mcp" then (($tool_name_canonical_raw // $tool_name_raw) | normalize_text)
      elif $invocation_origin == "plugin" then (($tool_name_canonical_raw // $tool_name_raw) | normalize_text)
      else null
      end
    ) as $invocation_name |
    {
      tool_name: $tool_name_raw,
      mode: (
        .mode // .chat_mode // .chatMode // .copilot_mode // .copilotMode //
        .invocation.mode // .payload.mode // .payload.chat_mode // .payload.chatMode //
        .request.mode // .request.chat_mode // .request.chatMode // null | sanitize_mode
      ),
      execution_mode: (
        $tool_input.mode // $tool_input.execution_mode // $tool_input.executionMode //
        .execution_mode // .executionMode // .tool_mode // .toolMode //
        .payload.tool_mode // .payload.toolMode //
        .payload.tool_input.mode // .payload.tool_input.execution_mode // .payload.tool_input.executionMode //
        .request.tool_mode // .request.toolMode // null | sanitize_mode
      ),
      tool_input_summary: ($tool_input | summarize),
      tool_result_summary: ($tool_result | summarize),
      invocation_origin: $invocation_origin,
      invocation_name: $invocation_name,
      skill_name: (if $invocation_origin == "skill" then $invocation_name else null end),
      custom_agent_name: (if $invocation_origin == "custom_agent" then $invocation_name else null end),
      mcp_name: (if $invocation_origin == "mcp" then $invocation_name else null end),
      plugin_name: (if $invocation_origin == "plugin" then $invocation_name else null end),
      status: (
        .status // .reason // $tool_result.resultType // $tool_result.status //
        (if ($tool_result.success? == true) then "success" elif ($tool_result.success? == false) then "failure" else null end)
      ),
      duration_ms: (.duration_ms // .durationMs // .payload.duration_ms // null),
      command: (.command // .payload.command // $tool_input.command // $tool_input.cmd // $tool_input.script // null)
    }
  ' <<< "$payload"
}

sanitize_payload() {
  local payload="$1"
  if ! logger_bool_true "$SESSION_LOGGER_REDACT_SECRETS"; then
    jq -c . <<< "$payload"
    return 0
  fi
  jq -c '
    def dedupe_extracted_keys:
      if type == "object" then
        (with_entries(.value |= dedupe_extracted_keys)) as $obj |
        reduce ($obj | keys_unsorted[]) as $key ($obj;
          if ($key | endswith("_extracted")) then
            ($key | sub("_extracted$"; "")) as $base_key |
            if (.[$base_key]? != null and .[$base_key] == .[$key]) then del(.[$key]) else . end
          else
            .
          end
        )
      elif type == "array" then map(dedupe_extracted_keys)
      else .
      end;
    def sensitive_key:
      test("token|password|passwd|pwd|secret|api[_-]?key|access[_-]?key|authorization|credential|private[_-]?key|openai[_-]?key|anthropic[_-]?key|github[_-]?token|aws[_-]?(secret[_-]?access[_-]?key|access[_-]?key)"; "i");
    def redact_string:
      gsub("-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]+?-----END [A-Z ]*PRIVATE KEY-----"; "[REDACTED:PRIVATE_KEY]") |
      gsub("github_pat_[A-Za-z0-9_]{20,}"; "[REDACTED:GITHUB_TOKEN]") |
      gsub("\\bgh[pousr]_[A-Za-z0-9_]{20,}\\b"; "[REDACTED:GITHUB_TOKEN]") |
      gsub("\\bAKIA[0-9A-Z]{16}\\b"; "[REDACTED:AWS_ACCESS_KEY_ID]") |
      gsub("\\bASIA[0-9A-Z]{16}\\b"; "[REDACTED:AWS_ACCESS_KEY_ID]") |
      gsub("\\bsk-(proj-)?[A-Za-z0-9_-]{20,}\\b"; "[REDACTED:OPENAI_KEY]") |
      gsub("\\bsk-ant-[A-Za-z0-9_-]{10,}\\b"; "[REDACTED:ANTHROPIC_KEY]") |
      gsub("\\beyJ[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\b"; "[REDACTED:JWT]") |
      gsub("(?i)(password\\s*[:=]\\s*)([^\\s,;]+)"; "\\1[REDACTED]") |
      gsub("(?i)(secret\\s*[:=]\\s*)([^\\s,;]+)"; "\\1[REDACTED]") |
      gsub("(?i)(api[_-]?key\\s*[:=]\\s*)([^\\s,;]+)"; "\\1[REDACTED]") |
      gsub("(?i)(bearer\\s+)([A-Za-z0-9\\-._~+/]+=*)"; "\\1[REDACTED]");
    def scrub:
      if type == "object" then
        with_entries(.value = (if (.key | sensitive_key) then "[REDACTED]" else (.value | scrub) end))
      elif type == "array" then map(scrub)
      elif type == "string" then redact_string
      else .
      end;
    scrub | dedupe_extracted_keys
  ' <<< "$payload"
}

build_normalized_event() {
  local payload="$1"
  local hook_event_type="$2"
  local event_id="$3"
  local session_id="$4"
  local user_prompt_id="$5"
  local parent_user_prompt_id="$6"
  local git_context="$7"
  local actor="$8"
  local metadata_json="${9}"
  [ -z "$metadata_json" ] && metadata_json="{}"
  local now
  local sanitized_payload
  local tool_metadata
  local normalized_event_type
  local copilot_user

  now="$(logger_now)"
  sanitized_payload="$(sanitize_payload "$payload")"
  tool_metadata="$(extract_tool_metadata "$sanitized_payload")"
  normalized_event_type="$(normalize_event_type "$hook_event_type")"
  copilot_user="$(extract_copilot_user "$sanitized_payload")"

  jq -cn \
    --argjson payload "$sanitized_payload" \
    --argjson git "$git_context" \
    --argjson tool "$tool_metadata" \
    --argjson extra_metadata "$metadata_json" \
    --arg event_id "$event_id" \
    --arg session_id "$session_id" \
    --arg hook_event_type "$hook_event_type" \
    --arg event_type "$normalized_event_type" \
    --arg userPrompt_id "$user_prompt_id" \
    --arg parent_userPrompt_id "$parent_user_prompt_id" \
    --arg actor "$actor" \
    --arg source "$SESSION_LOGGER_SOURCE" \
    --arg version "$SESSION_LOGGER_VERSION" \
    --arg copilot_user "$copilot_user" \
    --arg now "$now" \
    '
      def first(paths):
        reduce paths[] as $path (null; if . != null then . else ($payload | getpath($path)? // null) end);
      def as_string:
        if . == null or . == "" then null
        elif type == "string" then .
        else tojson
        end;
      def as_string_array:
        if . == null then []
        elif type == "array" then map(tostring)
        elif type == "string" and length > 0 then [.]
        else [tostring]
        end;
      def timestamp_value:
        first([["timestamp"], ["payload","timestamp"]]) as $ts |
        if $ts == null or $ts == "" then $now
        elif ($ts | type) == "number" then
          (if $ts > 10000000000 then ($ts / 1000) else $ts end | todateiso8601)
        elif ($ts | type) == "string" then $ts
        else $now
        end;
      def command_array:
        (first([["commands_executed"], ["commands"], ["payload","commands_executed"]]) | as_string_array) as $commands |
        if $tool.command == null then $commands else ($commands + [$tool.command | tostring]) end;
      def parse_jsonish:
        if type == "string" then (fromjson? // .) else . end;
      def from_tool_paths($value):
        ($value | parse_jsonish) as $parsed |
        [
          ($parsed.filePath // null),
          ($parsed.file_path // null),
          ($parsed.path // null),
          ($parsed.files // null),
          ($parsed.filePaths // null),
          ($parsed.paths // null),
          ($parsed.attachments // null),
          ($parsed.attachment_files // null),
          ($parsed.input_files // null),
          ($parsed.context_files // null),
          ($parsed.images // null),
          ($parsed.imagePaths // null),
          ($parsed.image_path // null)
        ]
        | map(
            if . == null then []
            elif type == "array" then map(tostring)
            elif type == "string" and length > 0 then [.]
            else []
            end
          )
        | add;
      def files_array:
        ((first([["files_touched"], ["files_changed"], ["filesChanged"], ["files"], ["payload","files_touched"], ["payload","files_changed"], ["payload","filesChanged"], ["toolResult","files_touched"], ["toolResult","files_changed"], ["toolResult","filesChanged"]]) | as_string_array) + ($git.files_changed // [])) | unique;
      def files_added_array:
        (
          (first([["files_added"], ["added_files"], ["new_files"], ["created_files"], ["filesAdded"], ["addedFiles"], ["newFiles"], ["createdFiles"], ["attachments"], ["attached_files"], ["attachment_files"], ["payload","files_added"], ["payload","added_files"], ["payload","filesAdded"], ["payload","addedFiles"], ["payload","attachments"], ["payload","attached_files"], ["payload","attachment_files"], ["toolResult","files_added"], ["toolResult","added_files"], ["toolResult","filesAdded"], ["toolResult","addedFiles"]]) | as_string_array)
          + from_tool_paths(first([["toolArgs"], ["tool_args"], ["tool_input"], ["payload","toolArgs"], ["payload","tool_input"], ["request","toolArgs"]]))
          + from_tool_paths(first([["toolResult"], ["tool_result"], ["payload","toolResult"]]))
        )
        | map(select(length > 0))
        | unique;
      def source_payload:
        first([["source"], ["payload","source"]]) | as_string;
      {
        event_id:$event_id,
        session_id:$session_id,
        timestamp:timestamp_value,
        event_type:$event_type,
        userPrompt_id:(if $userPrompt_id == "" then null else $userPrompt_id end),
        parent_userPrompt_id:(if $parent_userPrompt_id == "" then null else $parent_userPrompt_id end),
        actor:(if $actor == "" then null else $actor end),
        user_id:(if $actor == "" then null else $actor end),
        source:$source,
        repository:(first([["repository"], ["repo_name"], ["repositoryName"], ["payload","repository"]]) // $git.repo_name | as_string),
        branch:(first([["branch"], ["git_branch"], ["payload","branch"]]) // $git.git_branch | as_string),
        workspace:(first([["workspace"], ["cwd"], ["workingDirectory"], ["working_directory"], ["payload","cwd"]]) | as_string),
        mode:($tool.mode | as_string),
        execution_mode:($tool.execution_mode | as_string),
        invocation_origin:($tool.invocation_origin | as_string),
        invocation_name:($tool.invocation_name | as_string),
        tool_name:($tool.tool_name | as_string),
        tool_input_summary:($tool.tool_input_summary | as_string),
        tool_result_summary:($tool.tool_result_summary | as_string),
        prompt_text:(first([["prompt"], ["userPrompt"], ["message"], ["input"], ["text"], ["initialPrompt"], ["request","prompt"], ["payload","prompt"]]) | as_string),
        assistant_response_summary:(first([["assistant_response_summary"], ["assistantResponse"], ["assistant_response"], ["response"], ["payload","assistant_response"]]) | as_string),
        files_touched:files_array,
        files_added:files_added_array,
        commands_executed:command_array,
        status:($tool.status | as_string),
        duration_ms:($tool.duration_ms | if . == null or . == "" then null else tonumber? end),
        metadata:(
          {
            hook_event_type:$hook_event_type,
            logger_version:$version,
            payload_source:source_payload,
            mode:($tool.mode | as_string),
            execution_mode:($tool.execution_mode | as_string),
            invocation_origin:($tool.invocation_origin | as_string),
            invocation_name:($tool.invocation_name | as_string),
            skill_name:($tool.skill_name | as_string),
            custom_agent_name:($tool.custom_agent_name | as_string),
            mcp_name:($tool.mcp_name | as_string),
            plugin_name:($tool.plugin_name | as_string),
            is_mcp:($tool.invocation_origin == "mcp"),
            is_skill:($tool.invocation_origin == "skill"),
            is_plugin:($tool.invocation_origin == "plugin"),
            is_custom_agent:($tool.invocation_origin == "custom_agent"),
            files_added_count:(files_added_array | length),
            copilot_user:(if $copilot_user == "" then null else $copilot_user end),
            git:$git
          } + $extra_metadata
        ),
        raw_payload:$payload,
        created_at:$now
      }
    '
}
