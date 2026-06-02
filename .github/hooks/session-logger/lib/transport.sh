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
  local last_error="${2:-transport_send_failed}"
  local queue_path="$SESSION_LOGGER_QUEUE_DIR/pending.jsonl"
  mkdir -p "$SESSION_LOGGER_QUEUE_DIR"
  jq -cn \
    --argjson event "$event_json" \
    --arg last_error "$last_error" \
    --arg queued_at "$(logger_now)" \
    '{event_id:$event.event_id,event:$event,retry_count:0,last_error:$last_error,queued_at:$queued_at,updated_at:$queued_at}' >> "$queue_path"
}

normalize_otlp_base_endpoint() {
  local endpoint="$1"
  endpoint="${endpoint%/}"
  printf '%s\n' "$endpoint"
}

hash_hex_256() {
  local text="$1"
  if command -v shasum >/dev/null 2>&1; then
    printf '%s' "$text" | shasum -a 256 | awk '{print $1}'
    return 0
  fi
  if command -v openssl >/dev/null 2>&1; then
    printf '%s' "$text" | openssl dgst -sha256 | awk '{print $NF}'
    return 0
  fi
  printf '%s' "$(date +%s%N)-$$-$text" | tr -cd '0-9a-f'
}

build_trace_id_from_event() {
  local event_json="$1"
  local seed
  local hex
  seed="$(jq -r '.event_id // .session_id // .timestamp // "session-logger"' <<< "$event_json")"
  hex="$(hash_hex_256 "$seed" | tr '[:upper:]' '[:lower:]' | tr -cd '0-9a-f')"
  hex="${hex}00000000000000000000000000000000"
  printf '%s\n' "${hex:0:32}"
}

build_span_id_from_event() {
  local event_json="$1"
  local seed
  local hex
  seed="$(jq -r '.event_id // .session_id // .event_type // "session-logger"' <<< "$event_json"):span"
  hex="$(hash_hex_256 "$seed" | tr '[:upper:]' '[:lower:]' | tr -cd '0-9a-f')"
  hex="${hex}0000000000000000"
  printf '%s\n' "${hex:0:16}"
}

event_timestamp_ns() {
  local _event_json="$1"
  jq -rn '(now * 1000000000 | floor | tostring)'
}

build_otlp_attributes_from_event() {
  local event_json="$1"
  jq -cn --argjson event "$event_json" '
    def to_any:
      if type == "string" then {stringValue:.}
      elif type == "boolean" then {boolValue:.}
      elif type == "number" then
        if floor == . then {intValue:(tostring)} else {doubleValue:.} end
      elif type == "array" then {stringValue:(tojson)}
      elif type == "object" then {stringValue:(tojson)}
      elif type == "null" then {stringValue:"null"}
      else {stringValue:(tostring)}
      end;
    ($event | to_entries | map({key:.key, value:(.value|to_any)}))
  '
}

build_metric_attributes_from_event() {
  local event_json="$1"
  jq -cn --argjson event "$event_json" '
    [
      {key:"event_type", value:{stringValue:($event.event_type // "unknown")}},
      {key:"repository", value:{stringValue:($event.repository // "unknown")}},
      {key:"branch", value:{stringValue:($event.branch // "unknown")}},
      {key:"source", value:{stringValue:($event.source // "unknown")}},
      {key:"tool_name", value:{stringValue:($event.tool_name // "none")}},
      {key:"status", value:{stringValue:($event.status // "unset")}}
    ]
  '
}

build_otlp_trace_payload() {
  local event_json="$1"
  local trace_id="$2"
  local span_id="$3"
  local start_ns="$4"
  local end_ns="$5"
  local attrs
  attrs="$(build_otlp_attributes_from_event "$event_json")"

  jq -cn \
    --argjson event "$event_json" \
    --arg trace_id "$trace_id" \
    --arg span_id "$span_id" \
    --arg start_ns "$start_ns" \
    --arg end_ns "$end_ns" \
    --argjson attrs "$attrs" \
    '
      {
        resourceSpans: [
          {
            resource: {
              attributes: [
                {key:"service.name", value:{stringValue:"session-logger"}},
                {key:"service.namespace", value:{stringValue:"marvin"}},
                {key:"service.instance.id", value:{stringValue:(($event.session_id // "unknown") + ":" + ($event.event_id // "unknown"))}}
              ]
            },
            scopeSpans: [
              {
                scope: {name:"session-logger-shell", version:"0.2.0-shell"},
                spans: [
                  {
                    traceId: $trace_id,
                    spanId: $span_id,
                    name: ($event.event_type // "session_logger_event"),
                    kind: 1,
                    startTimeUnixNano: $start_ns,
                    endTimeUnixNano: $end_ns,
                    attributes: ($attrs + [{key:"stack.signal", value:{stringValue:"tempo"}}]),
                    status: {code: 1}
                  }
                ]
              }
            ]
          }
        ]
      }
    '
}

build_otlp_metric_payload() {
  local event_json="$1"
  local ts_ns="$2"
  local metric_attrs
  metric_attrs="$(build_metric_attributes_from_event "$event_json")"

  jq -cn \
    --argjson event "$event_json" \
    --arg ts_ns "$ts_ns" \
    --argjson metric_attrs "$metric_attrs" \
    '
      {
        resourceMetrics: [
          {
            resource: {
              attributes: [
                {key:"service.name", value:{stringValue:"session-logger"}},
                {key:"service.namespace", value:{stringValue:"marvin"}}
              ]
            },
            scopeMetrics: [
              {
                scope: {name:"session-logger-shell", version:"0.2.0-shell"},
                metrics: [
                  {
                    name: "session_logger_events_total",
                    description: "Events captured by session-logger shell hook",
                    unit: "1",
                    sum: {
                      aggregationTemporality: 2,
                      isMonotonic: true,
                      dataPoints: [
                        {
                          timeUnixNano: $ts_ns,
                          asInt: "1",
                          attributes: $metric_attrs
                        }
                      ]
                    }
                  }
                ]
              }
            ]
          }
        ]
      }
    '
}

send_otlp_payload() {
  local endpoint="$1"
  local payload="$2"
  local signal_name="$3"
  local body_file
  local response_file
  local error_file
  local http_code
  local curl_exit

  body_file="$(mktemp)"
  response_file="$(mktemp)"
  error_file="$(mktemp)"
  printf '%s\n' "$payload" > "$body_file"

  set +e
  http_code="$({
    curl -sS \
      -o "$response_file" \
      -w "%{http_code}" \
      --max-time "$SESSION_LOGGER_TIMEOUT_SECONDS" \
      -X POST "$endpoint" \
      -H "Content-Type: application/json" \
      --data-binary "@$body_file" 2>"$error_file"
  })"
  curl_exit=$?
  set -e

  rm -f "$body_file" "$response_file"
  if [ "$curl_exit" -eq 0 ] && [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    rm -f "$error_file"
    return 0
  fi

  local error_message
  error_message="otlp_${signal_name}_http_${http_code:-000}_curl_${curl_exit}"
  if [ -s "$error_file" ]; then
    error_message="$error_message:$(tr '\n' ' ' < "$error_file" | cut -c1-200)"
  fi
  rm -f "$error_file"
  json_log "warn" "otlp_send_failed" "$error_message"
  return 1
}

send_event_to_otlp_target() {
  local event_json="$1"
  if [ -z "$SESSION_LOGGER_OTLP_ENDPOINT" ]; then
    json_log "warn" "otlp_not_configured" "otlp endpoint missing"
    return 1
  fi

  local base_endpoint
  local trace_id
  local span_id
  local start_ns
  local end_ns
  local trace_payload
  local metric_payload
  local otlp_send_status=0

  base_endpoint="$(normalize_otlp_base_endpoint "$SESSION_LOGGER_OTLP_ENDPOINT")"
  trace_id="$(build_trace_id_from_event "$event_json")"
  span_id="$(build_span_id_from_event "$event_json")"
  start_ns="$(event_timestamp_ns "$event_json")"
  end_ns="$((start_ns + 1000))"

  trace_payload="$(build_otlp_trace_payload "$event_json" "$trace_id" "$span_id" "$start_ns" "$end_ns")" || return 1
  metric_payload="$(build_otlp_metric_payload "$event_json" "$end_ns")" || return 1

  send_otlp_payload "$base_endpoint/v1/traces" "$trace_payload" "traces" || otlp_send_status=1
  send_otlp_payload "$base_endpoint/v1/metrics" "$metric_payload" "metrics" || otlp_send_status=1
  return "$otlp_send_status"
}

send_event_to_api_target() {
  local event_json="$1"
  if [ -z "$SESSION_LOGGER_ENDPOINT" ] || [ -z "$SESSION_LOGGER_API_KEY" ]; then
    json_log "warn" "http_not_configured" "endpoint or token missing"
    return 1
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
  return 1
}

build_loki_payload() {
  local event_json="$1"
  jq -cn \
    --argjson event "$event_json" \
    --arg source "$SESSION_LOGGER_SOURCE" \
    '
      (now * 1000000000 | floor | tostring) as $ingest_ns |
      {
        streams: [
          {
            stream: {
              job: "session-logger-shell",
              service_name: "session-logger",
              source: $source,
              event_type: ($event.event_type // "unknown"),
              session_id: ($event.session_id // "unknown"),
              repository: ($event.repository // "unknown"),
              branch: ($event.branch // "unknown"),
              mode: ($event.mode // $event.metadata.mode // "unknown"),
              execution_mode: ($event.execution_mode // $event.metadata.execution_mode // "unknown"),
              invocation_origin: ($event.invocation_origin // $event.metadata.invocation_origin // "unknown"),
              actor: ($event.actor // $event.user_id // "unknown"),
              files_added_count: ((($event.files_added // []) | length) | tostring)
            },
            values: [[$ingest_ns, ($event | tojson)]]
          }
        ]
      }
    '
}

send_event_to_loki_target() {
  local event_json="$1"
  if [ -z "$SESSION_LOGGER_LOKI_ENDPOINT" ]; then
    json_log "warn" "loki_not_configured" "loki endpoint missing"
    return 1
  fi

  local body_file
  local response_file
  local error_file
  local http_code
  local curl_exit
  local loki_payload
  body_file="$(mktemp)"
  response_file="$(mktemp)"
  error_file="$(mktemp)"
  loki_payload="$(build_loki_payload "$event_json")" || {
    rm -f "$body_file" "$response_file" "$error_file"
    return 1
  }
  printf '%s\n' "$loki_payload" > "$body_file"

  local -a headers
  headers=(-H "Content-Type: application/json")
  if [ -n "$SESSION_LOGGER_LOKI_TENANT_ID" ]; then
    headers+=(-H "X-Scope-OrgID: $SESSION_LOGGER_LOKI_TENANT_ID")
  fi

  set +e
  http_code="$({
    curl -sS \
      -o "$response_file" \
      -w "%{http_code}" \
      --max-time "$SESSION_LOGGER_TIMEOUT_SECONDS" \
      -X POST "$SESSION_LOGGER_LOKI_ENDPOINT" \
      "${headers[@]}" \
      --data-binary "@$body_file" 2>"$error_file"
  })"
  curl_exit=$?
  set -e

  rm -f "$body_file" "$response_file"
  if [ "$curl_exit" -eq 0 ] && [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
    rm -f "$error_file"
    return 0
  fi

  local error_message
  error_message="loki_http_${http_code:-000}_curl_${curl_exit}"
  if [ -s "$error_file" ]; then
    error_message="$error_message:$(tr '\n' ' ' < "$error_file" | cut -c1-200)"
  fi
  rm -f "$error_file"
  json_log "warn" "loki_send_failed" "$error_message"
  return 1
}

send_event_to_destinations() {
  local event_json="$1"
  local queue_on_failure="${2:-true}"
  local attempted=0
  local succeeded=0
  local errors=()

  if logger_bool_true "$SESSION_LOGGER_HTTP_ENABLED"; then
    attempted=$((attempted + 1))
    if send_event_to_api_target "$event_json"; then
      succeeded=$((succeeded + 1))
    else
      errors+=("http_failed")
    fi
  fi

  if logger_bool_true "$SESSION_LOGGER_LOKI_ENABLED"; then
    attempted=$((attempted + 1))
    if send_event_to_loki_target "$event_json"; then
      succeeded=$((succeeded + 1))
    else
      errors+=("loki_failed")
    fi
  fi

  if logger_bool_true "$SESSION_LOGGER_OTLP_ENABLED"; then
    attempted=$((attempted + 1))
    if send_event_to_otlp_target "$event_json"; then
      succeeded=$((succeeded + 1))
    else
      errors+=("otlp_failed")
    fi
  fi

  if [ "$attempted" -eq 0 ]; then
    return 0
  fi

  if [ "$succeeded" -eq "$attempted" ]; then
    return 0
  fi

  if logger_bool_true "$queue_on_failure" && logger_bool_true "$SESSION_LOGGER_OFFLINE_QUEUE_ENABLED"; then
    queue_event_for_retry "$event_json" "$(IFS=,; echo "${errors[*]}")"
    return 0
  fi

  return 1
}

send_event_to_api() {
  local event_json="$1"
  local queue_on_failure="${2:-true}"
  send_event_to_destinations "$event_json" "$queue_on_failure"
}

flush_offline_queue() {
  if ! logger_bool_true "$SESSION_LOGGER_HTTP_ENABLED" && ! logger_bool_true "$SESSION_LOGGER_LOKI_ENABLED" && ! logger_bool_true "$SESSION_LOGGER_OTLP_ENABLED"; then
    jq -cn '{http_enabled:false,loki_enabled:false,otlp_enabled:false,flushed:false,reason:"all_transports_disabled"}'
    return 0
  fi
  local pending_path="$SESSION_LOGGER_QUEUE_DIR/pending.jsonl"
  local tmp_path="$SESSION_LOGGER_QUEUE_DIR/pending.tmp"
  local sent_path="$SESSION_LOGGER_QUEUE_DIR/sent.jsonl"
  mkdir -p "$SESSION_LOGGER_QUEUE_DIR"
  if [ ! -f "$pending_path" ]; then
    jq -cn \
      --argjson http_enabled "$(logger_bool_true "$SESSION_LOGGER_HTTP_ENABLED" && echo true || echo false)" \
      --argjson loki_enabled "$(logger_bool_true "$SESSION_LOGGER_LOKI_ENABLED" && echo true || echo false)" \
      --argjson otlp_enabled "$(logger_bool_true "$SESSION_LOGGER_OTLP_ENABLED" && echo true || echo false)" \
      '{http_enabled:$http_enabled,loki_enabled:$loki_enabled,otlp_enabled:$otlp_enabled,flushed:true,attempted:0,sent:0,remaining:0}'
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
    send_event_to_destinations "$event_json" false
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
    --argjson http_enabled "$(logger_bool_true "$SESSION_LOGGER_HTTP_ENABLED" && echo true || echo false)" \
    --argjson loki_enabled "$(logger_bool_true "$SESSION_LOGGER_LOKI_ENABLED" && echo true || echo false)" \
    --argjson otlp_enabled "$(logger_bool_true "$SESSION_LOGGER_OTLP_ENABLED" && echo true || echo false)" \
    --argjson attempted "$attempted" \
    --argjson sent "$sent" \
    --argjson remaining "$(wc -l < "$pending_path" | tr -d ' ')" \
    '{http_enabled:$http_enabled,loki_enabled:$loki_enabled,otlp_enabled:$otlp_enabled,flushed:true,attempted:$attempted,sent:$sent,remaining:$remaining}'
}
