#!/usr/bin/env bash
set -euo pipefail

generate_uuid() {
  if [ -r /proc/sys/kernel/random/uuid ]; then
    tr -d '\n' < /proc/sys/kernel/random/uuid
    return
  fi
  if command -v uuidgen >/dev/null 2>&1; then
    uuidgen | tr '[:upper:]' '[:lower:]'
    return
  fi
  printf '%s-%s-%s' "$(date -u +%s)" "$$" "${RANDOM:-0}"
}

generate_event_id() {
  printf 'evt_%s\n' "$(generate_uuid)"
}

generate_userPrompt_id() {
  printf 'up_%s\n' "$(generate_uuid)"
}

generate_session_id() {
  printf 'sess_%s\n' "$(generate_uuid)"
}

state_file_for_session() {
  local session_id="$1"
  printf '%s/%s.json\n' "$SESSION_LOGGER_STATE_DIR" "$(safe_file_key "$session_id")"
}

get_last_userPrompt_id() {
  local session_id="$1"
  local state_file
  state_file="$(state_file_for_session "$session_id")"
  if [ ! -f "$state_file" ]; then
    return 0
  fi
  jq -r '.last_userPrompt_id // empty' "$state_file" 2>/dev/null || true
}

set_last_userPrompt_id() {
  local session_id="$1"
  local user_prompt_id="$2"
  local state_file
  local tmp_file
  state_file="$(state_file_for_session "$session_id")"
  tmp_file="${state_file}.tmp"
  mkdir -p "$SESSION_LOGGER_STATE_DIR"
  jq -cn \
    --arg session_id "$session_id" \
    --arg userPrompt_id "$user_prompt_id" \
    --arg updated_at "$(logger_now)" \
    '{session_id:$session_id,last_userPrompt_id:$userPrompt_id,updated_at:$updated_at}' > "$tmp_file"
  mv "$tmp_file" "$state_file"
}

resolve_parent_userPrompt_id() {
  local normalized_event_type="$1"
  local session_id="$2"
  local explicit_parent="${3:-}"

  if [ "$normalized_event_type" = "user_prompt" ]; then
    return 0
  fi
  if [ -n "$explicit_parent" ] && [ "$explicit_parent" != "null" ]; then
    printf '%s\n' "$explicit_parent"
    return 0
  fi
  get_last_userPrompt_id "$session_id"
}

session_index_path() {
  printf '%s/session-index.json\n' "$SESSION_LOGGER_STATE_DIR"
}

get_cached_session_id() {
  local scope_key="$1"
  local index_file
  index_file="$(session_index_path)"
  if [ ! -f "$index_file" ]; then
    return 0
  fi
  jq -r --arg key "$scope_key" '.[$key].session_id // empty' "$index_file" 2>/dev/null || true
}

set_cached_session_id() {
  local scope_key="$1"
  local session_id="$2"
  local index_file
  local tmp_file
  index_file="$(session_index_path)"
  tmp_file="${index_file}.tmp"
  mkdir -p "$SESSION_LOGGER_STATE_DIR"
  if [ -f "$index_file" ]; then
    jq \
      --arg key "$scope_key" \
      --arg session_id "$session_id" \
      --arg updated_at "$(logger_now)" \
      '.[$key] = {session_id:$session_id, updated_at:$updated_at}' "$index_file" > "$tmp_file"
  else
    jq -cn \
      --arg key "$scope_key" \
      --arg session_id "$session_id" \
      --arg updated_at "$(logger_now)" \
      '{($key): {session_id:$session_id, updated_at:$updated_at}}' > "$tmp_file"
  fi
  mv "$tmp_file" "$index_file"
}

clear_cached_session_id() {
  local scope_key="$1"
  local index_file
  local tmp_file
  index_file="$(session_index_path)"
  [ -f "$index_file" ] || return 0
  tmp_file="${index_file}.tmp"
  jq --arg key "$scope_key" 'del(.[$key])' "$index_file" > "$tmp_file"
  mv "$tmp_file" "$index_file"
}

resolve_session_id() {
  local explicit_session_id="$1"
  local hook_event_type="$2"
  local scope_key="$3"
  local persist_state="${4:-true}"
  local cached=""
  local session_id=""

  if [ -n "$explicit_session_id" ] && [ "$explicit_session_id" != "null" ]; then
    session_id="$explicit_session_id"
  elif [ "$hook_event_type" = "sessionStart" ] || [ "$hook_event_type" = "session_start" ]; then
    session_id="$(generate_session_id)"
  else
    cached="$(get_cached_session_id "$scope_key")"
    session_id="${cached:-$(generate_session_id)}"
  fi

  if logger_bool_true "$persist_state"; then
    if [ "$hook_event_type" = "sessionEnd" ] || [ "$hook_event_type" = "session_end" ]; then
      clear_cached_session_id "$scope_key"
    else
      set_cached_session_id "$scope_key" "$session_id"
    fi
  fi
  printf '%s\n' "$session_id"
}
