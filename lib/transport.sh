#!/usr/bin/env bash
set -euo pipefail

write_jsonl_event() {
  local event_json="$1"
  local timestamp
  local date_dir
  local output_path
  timestamp="$(jq -r '.timestamp // empty' <<< "$event_json")"
  date_dir="${timestamp:0:10}"
  if [ -z "$date_dir" ] || [ "$date_dir" = "null" ]; then
    date_dir="$(date -u +%Y-%m-%d)"
  fi
  output_path="$SESSION_LOGGER_LOGS_DIR/$date_dir/events.jsonl"
  mkdir -p "$(dirname "$output_path")"
  jq -c . <<< "$event_json" >> "$output_path"
  printf '%s\n' "$output_path"
}

queue_event_for_retry() {
  local event_json="$1"
  local last_error="${2:-send_failed}"
  local queue_path="$SESSION_LOGGER_QUEUE_DIR/pending.jsonl"
  mkdir -p "$SESSION_LOGGER_QUEUE_DIR"
  jq -cn \
    --argjson event "$event_json" \
    --arg last_error "$last_error" \
    --arg queued_at "$(logger_now)" \
    '{event_id:$event.event_id,event:$event,retry_count:0,last_error:$last_error,queued_at:$queued_at,updated_at:$queued_at}' >> "$queue_path"
}

send_event_to_api() {
  local event_json="$1"
  local queue_on_failure="${2:-true}"
  if ! logger_bool_true "$SESSION_LOGGER_HTTP_ENABLED"; then
    return 0
  fi
  if [ -z "$SESSION_LOGGER_ENDPOINT" ] || [ -z "$SESSION_LOGGER_API_KEY" ]; then
    json_log "warn" "http_not_configured" "endpoint or token missing"
    if ! logger_bool_true "$queue_on_failure"; then
      return 1
    fi
    return 0
  fi

  local body_file
  local response_file
  local error_file
  local http_code
  local curl_exit
  body_file="$(mktemp)"
  response_file="$(mktemp)"
  error_file="$(mktemp)"
  jq -c . <<< "$event_json" > "$body_file"

  set +e
  http_code="$(
    curl -sS \
      -o "$response_file" \
      -w "%{http_code}" \
      --max-time "$SESSION_LOGGER_TIMEOUT_SECONDS" \
      -X POST "$SESSION_LOGGER_ENDPOINT" \
      -H "Content-Type: application/json" \
      -H "Accept: application/json" \
      -H "Authorization: Bearer $SESSION_LOGGER_API_KEY" \
      -H "X-Logger-Token: $SESSION_LOGGER_API_KEY" \
      -H "X-Logger-Version: $SESSION_LOGGER_VERSION" \
      --data-binary "@$body_file" 2>"$error_file"
  )"
  curl_exit=$?
  set -e

  rm -f "$body_file" "$response_file"
  if [ "$curl_exit" -eq 0 ] && [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    rm -f "$error_file"
    return 0
  fi

  local error_message
  error_message="http_${http_code:-000}_curl_${curl_exit}"
  if [ -s "$error_file" ]; then
    error_message="$error_message:$(tr '\n' ' ' < "$error_file" | cut -c1-200)"
  fi
  rm -f "$error_file"

  json_log "warn" "http_send_failed" "$error_message"
  if logger_bool_true "$queue_on_failure" && logger_bool_true "$SESSION_LOGGER_OFFLINE_QUEUE_ENABLED"; then
    queue_event_for_retry "$event_json" "$error_message"
    return 0
  fi
  return 1
}

flush_offline_queue() {
  if ! logger_bool_true "$SESSION_LOGGER_HTTP_ENABLED"; then
    jq -cn '{http_enabled:false,flushed:false,reason:"http_disabled"}'
    return 0
  fi
  local pending_path="$SESSION_LOGGER_QUEUE_DIR/pending.jsonl"
  local tmp_path="$SESSION_LOGGER_QUEUE_DIR/pending.tmp"
  local sent_path="$SESSION_LOGGER_QUEUE_DIR/sent.jsonl"
  mkdir -p "$SESSION_LOGGER_QUEUE_DIR"
  if [ ! -f "$pending_path" ]; then
    jq -cn '{http_enabled:true,flushed:true,attempted:0,sent:0,remaining:0}'
    return 0
  fi

  local attempted=0
  local sent=0
  : > "$tmp_path"
  while IFS= read -r line; do
    [ -n "${line//[[:space:]]/}" ] || continue
    attempted=$((attempted + 1))
    local event_json
    event_json="$(jq -c '.event // .' <<< "$line" 2>/dev/null || true)"
    if [ -z "$event_json" ]; then
      continue
    fi
    set +e
    send_event_to_api "$event_json" false
    local send_exit=$?
    set -e
    if [ "$send_exit" -eq 0 ]; then
      sent=$((sent + 1))
      jq -cn --argjson entry "$line" --arg sent_at "$(logger_now)" '$entry + {sent_at:$sent_at}' >> "$sent_path"
    else
      jq -c . <<< "$line" >> "$tmp_path"
    fi
  done < "$pending_path"
  mv "$tmp_path" "$pending_path"
  jq -cn \
    --argjson attempted "$attempted" \
    --argjson sent "$sent" \
    --argjson remaining "$(wc -l < "$pending_path" | tr -d ' ')" \
    '{http_enabled:true,flushed:true,attempted:$attempted,sent:$sent,remaining:$remaining}'
}
