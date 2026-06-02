#!/usr/bin/env bash
set -euo pipefail

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

build_loki_payload() {
  local event_json="$1"
  local logger_hostname
  logger_hostname="$(hostname 2>/dev/null || true)"
  if [ -z "$logger_hostname" ]; then
    logger_hostname="$(uname -n 2>/dev/null || true)"
  fi
  logger_hostname="${logger_hostname:-unknown}"
  jq -cn \
    --argjson event "$event_json" \
    --arg source "$SESSION_LOGGER_SOURCE" \
    --arg logger_hostname "$logger_hostname" \
    '
      (now * 1000000000 | floor | tostring) as $ingest_ns |
      {
        streams: [
          {
            stream: {
              job: "session-logger-shell",
              service_name: "session-logger",
              hostname: $logger_hostname,
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

send_event_to_observability() {
  local event_json="$1"
  local attempted=0
  local succeeded=0

  if logger_bool_true "$SESSION_LOGGER_LOKI_ENABLED"; then
    attempted=$((attempted + 1))
    if send_event_to_loki_target "$event_json"; then
      succeeded=$((succeeded + 1))
    fi
  fi

  if logger_bool_true "$SESSION_LOGGER_OTLP_ENABLED"; then
    attempted=$((attempted + 1))
    if send_event_to_otlp_target "$event_json"; then
      succeeded=$((succeeded + 1))
    fi
  fi

  if [ "$attempted" -eq 0 ]; then
    json_log "warn" "no_observability_transports_enabled" "enable loki and/or otlp"
    return 1
  fi

  if [ "$succeeded" -eq "$attempted" ]; then
    return 0
  fi

  return 1
}
