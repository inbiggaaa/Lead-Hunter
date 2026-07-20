#!/bin/bash
# LeadHunter Watchdog — проверяет контейнеры и алертит владельцу.
# Cron: */5 * * * * /opt/LeadHunter/scripts/watchdog.sh
#
# Checks:
#   1. All 5 containers running
#   2. Admin /health
#   3. Worker heartbeat age (wall-clock keys preferred; presence fallback)
#   4. Queue backlog + DLQ
#   5. Disk free space

set -euo pipefail

PROJECT_DIR="/opt/LeadHunter"
LOG_FILE="$PROJECT_DIR/logs/watchdog.log"
ALERT_COOLDOWN_FILE="/tmp/leadhunter_watchdog_last_alert"
ALERT_COOLDOWN=1800  # 30 minutes
HEARTBEAT_MAX_AGE_SEC=1200  # 20 minutes
QUEUE_ALERT_LEN=100
DISK_ALERT_PCT=90

declare -A EXPECTED=(
    [leadhunter-db-1]=""
    [leadhunter-redis-1]=""
    [leadhunter-bot-1]=""
    [leadhunter-worker-1]=""
    [leadhunter-admin-1]=""
)

send_alert() {
    local msg="$1"
    local now
    now=$(date +%s)

    if [ -f "$ALERT_COOLDOWN_FILE" ]; then
        local last
        last=$(cat "$ALERT_COOLDOWN_FILE")
        if [ $((now - last)) -lt $ALERT_COOLDOWN ]; then
            return 0
        fi
    fi

    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env" 2>/dev/null || true
    set +a

    # OWNER_TELEGRAM_ID is the config source of truth; ADMIN_TELEGRAM_ID kept as alias.
    local chat_id="${OWNER_TELEGRAM_ID:-${ADMIN_TELEGRAM_ID:-}}"
    if [ -z "$chat_id" ]; then
        echo "[$(date -Iseconds)] [ALERT] $msg (OWNER_TELEGRAM_ID not set)" >> "$LOG_FILE"
        return 0
    fi

    local full_msg="LeadHunter Watchdog — $(date '+%H:%M:%S')%0A$msg"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${chat_id}" \
        -d "text=${full_msg}" \
        -d "parse_mode=HTML" > /dev/null 2>&1 || true

    echo "$now" > "$ALERT_COOLDOWN_FILE"
    echo "[$(date -Iseconds)] [ALERT] $msg" >> "$LOG_FILE"
}

mkdir -p "$(dirname "$LOG_FILE")"
echo "[$(date -Iseconds)] [OK] Watchdog started" >> "$LOG_FILE"

cd "$PROJECT_DIR"
ISSUES=""

for container in "${!EXPECTED[@]}"; do
    state=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "MISSING")
    if [ "$state" != "running" ]; then
        svc_name=$(echo "$container" | sed 's/leadhunter-//;s/-[0-9]*$//')
        ISSUES="${ISSUES}• ${svc_name}: <b>${state}</b>%0A"
    fi
done

admin_health=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:17421/health 2>/dev/null || echo "000")
if [ "$admin_health" != "200" ]; then
    ISSUES="${ISSUES}• admin /health: <b>HTTP ${admin_health}</b>%0A"
fi

# Heartbeat: prefer wall-clock key if present; else presence-only legacy key.
heartbeat_wall=$(docker compose exec -T redis redis-cli GET "heartbeat:wall:userbot:1" 2>/dev/null || echo "")
if [ -n "$heartbeat_wall" ] && [[ "$heartbeat_wall" =~ ^[0-9]+$ ]]; then
    now_ts=$(date +%s)
    age=$((now_ts - heartbeat_wall))
    if [ "$age" -gt "$HEARTBEAT_MAX_AGE_SEC" ]; then
        ISSUES="${ISSUES}• worker heartbeat stale: <b>${age}s</b>%0A"
    fi
else
    heartbeat_ts=$(docker compose exec -T redis redis-cli GET "heartbeat:userbot:1" 2>/dev/null || echo "")
    if [ -z "$heartbeat_ts" ]; then
        ISSUES="${ISSUES}• worker heartbeat: <b>missing</b>%0A"
    fi
fi

queue_len=$(docker compose exec -T redis redis-cli LLEN queue:notifications 2>/dev/null || echo "0")
dlq_len=$(docker compose exec -T redis redis-cli LLEN dlq:notifications 2>/dev/null || echo "0")
if [[ "$queue_len" =~ ^[0-9]+$ ]] && [ "$queue_len" -gt "$QUEUE_ALERT_LEN" ]; then
    ISSUES="${ISSUES}• queue backlog: <b>${queue_len}</b>%0A"
fi
if [[ "$dlq_len" =~ ^[0-9]+$ ]] && [ "$dlq_len" -gt 0 ]; then
    ISSUES="${ISSUES}• DLQ: <b>${dlq_len}</b>%0A"
fi

disk_pct=$(df -P "$PROJECT_DIR" | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
if [[ "$disk_pct" =~ ^[0-9]+$ ]] && [ "$disk_pct" -ge "$DISK_ALERT_PCT" ]; then
    ISSUES="${ISSUES}• disk used: <b>${disk_pct}%</b>%0A"
fi

# LLM fail-open share for current UTC hour (A2).
hour_key=$(date -u +%Y-%m-%dT%H)
llm_total=$(docker compose exec -T redis redis-cli GET "stats:llm:total:${hour_key}" 2>/dev/null || echo "0")
llm_fail=$(docker compose exec -T redis redis-cli GET "stats:llm:fail_open:${hour_key}" 2>/dev/null || echo "0")
if [[ "$llm_total" =~ ^[0-9]+$ ]] && [[ "$llm_fail" =~ ^[0-9]+$ ]] && [ "$llm_total" -ge 20 ]; then
    # integer percent = fail*100/total
    fail_pct=$((llm_fail * 100 / llm_total))
    if [ "$fail_pct" -ge 50 ]; then
        ISSUES="${ISSUES}• LLM fail-open CRITICAL: <b>${fail_pct}%</b> (${llm_fail}/${llm_total})%0A"
    elif [ "$fail_pct" -ge 20 ]; then
        ISSUES="${ISSUES}• LLM fail-open WARNING: <b>${fail_pct}%</b> (${llm_fail}/${llm_total})%0A"
    fi
fi

if [ -n "$ISSUES" ]; then
    send_alert "$ISSUES"
fi

echo "[$(date -Iseconds)] [OK] Watchdog finished, issues=${ISSUES:-none}" >> "$LOG_FILE"
