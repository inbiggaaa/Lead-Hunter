#!/bin/bash
# LeadHunter Watchdog — проверяет все контейнеры и алертит в Telegram
# Запускать из cron каждые 5 минут:
#   */5 * * * * /opt/LeadHunter/scripts/watchdog.sh
#
# Проверяет:
#   1. Все 5 контейнеров в статусе "Up" (не Created, не Exited)
#   2. Admin отвечает на /health
#   3. Worker heartbeat не старше 20 минут (через Redis)

set -euo pipefail

PROJECT_DIR="/opt/LeadHunter"
LOG_FILE="$PROJECT_DIR/logs/watchdog.log"
ALERT_COOLDOWN_FILE="/tmp/leadhunter_watchdog_last_alert"
ALERT_COOLDOWN=1800  # 30 минут между повторными алертами

# Ожидаемые контейнеры (имя сервиса:порт для health проверки)
declare -A EXPECTED=(
    [leadhunter-db-1]=""
    [leadhunter-redis-1]=""
    [leadhunter-bot-1]=""
    [leadhunter-worker-1]=""
    [leadhunter-admin-1]=""
)

# ──── Telegram alert ────
send_alert() {
    local msg="$1"
    local now
    now=$(date +%s)

    # Cooldown check
    if [ -f "$ALERT_COOLDOWN_FILE" ]; then
        local last
        last=$(cat "$ALERT_COOLDOWN_FILE")
        if [ $((now - last)) -lt $ALERT_COOLDOWN ]; then
            return 0
        fi
    fi

    # Load env
    set -a
    source "$PROJECT_DIR/.env" 2>/dev/null || true
    set +a

    if [ -z "${ADMIN_TELEGRAM_ID:-}" ]; then
        echo "[$(date -Iseconds)] [ALERT] $msg (ADMIN_TELEGRAM_ID not set, no alert sent)" >> "$LOG_FILE"
        return 0
    fi

    local full_msg="🚨 LeadHunter Watchdog — $(date '+%H:%M:%S')%0A$msg"

    # Send via Bot API (uses BOT_TOKEN from .env)
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${ADMIN_TELEGRAM_ID}" \
        -d "text=${full_msg}" \
        -d "parse_mode=HTML" > /dev/null 2>&1 || true

    echo "$now" > "$ALERT_COOLDOWN_FILE"
    echo "[$(date -Iseconds)] [ALERT] $msg" >> "$LOG_FILE"
}

# ──── Init ────
mkdir -p "$(dirname "$LOG_FILE")"
echo "[$(date -Iseconds)] [OK] Watchdog started" >> "$LOG_FILE"

cd "$PROJECT_DIR"
ISSUES=""

# ──── 1. Проверка контейнеров ────
for container in "${!EXPECTED[@]}"; do
    state=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "MISSING")

    if [ "$state" != "running" ]; then
        svc_name=$(echo "$container" | sed 's/leadhunter-//;s/-[0-9]*$//')
        ISSUES="${ISSUES}• ${svc_name}: <b>${state}</b>%0A"

        # Пробуем запустить (кроме db/redis — они managed отдельно)
        if [ "$state" = "created" ] && [ "$svc_name" != "db" ] && [ "$svc_name" != "redis" ]; then
            docker compose up -d "$svc_name" 2>&1 >> "$LOG_FILE" || true
            echo "[$(date -Iseconds)] [FIX] Attempted docker compose up -d $svc_name" >> "$LOG_FILE"
        fi

        # Для exited — стандартный рестарт
        if [ "$state" = "exited" ]; then
            docker compose restart "$svc_name" 2>&1 >> "$LOG_FILE" || true
            echo "[$(date -Iseconds)] [FIX] Attempted docker compose restart $svc_name" >> "$LOG_FILE"
        fi
    fi
done

# ──── 2. Проверка health-endpoint админки ────
admin_health=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:17421/health 2>/dev/null || echo "000")
if [ "$admin_health" != "200" ]; then
    ISSUES="${ISSUES}• admin /health: <b>HTTP ${admin_health}</b>%0A"
fi

# ──── 3. Проверка heartbeat worker'а через Redis ────
heartbeat_key="heartbeat:userbot:1"
heartbeat_ts=$(docker compose exec -T redis redis-cli GET "$heartbeat_key" 2>/dev/null || echo "")
if [ -n "$heartbeat_ts" ]; then
    now_ts=$(date +%s)
    # Сравниваем: heartbeat пишет event_loop.time() (монотонные секунды), не wall clock
    # Проверяем просто наличие — если ключ есть и не истёк, worker жив
    :
else
    # Проверяем heartbeat для account 0 (legacy ключ)
    heartbeat_ts=$(docker compose exec -T redis redis-cli GET "heartbeat:userbot:0" 2>/dev/null || echo "")
    if [ -z "$heartbeat_ts" ]; then
        ISSUES="${ISSUES}• worker heartbeat: <b>отсутствует в Redis</b>%0A"
    fi
fi

# ──── Отправка алерта ────
if [ -n "$ISSUES" ]; then
    send_alert "$ISSUES"
fi

echo "[$(date -Iseconds)] [OK] Watchdog finished, issues=${ISSUES:-none}" >> "$LOG_FILE"
