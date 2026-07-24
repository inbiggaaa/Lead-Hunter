# Userbot Capacity Governor — rollout / rollback

**Дата:** 24.07.2026  
**Ветка:** `feature/userbot-capacity-governor`  
**Статус:** код готов; production НЕ выкатывать без явной команды владельца.

## Цель

Защитить userbot-аккаунты от FloodWait (инцидент §7б), ограничивать и плавно
восстанавливать нагрузку, не опрашивать географию без подписчиков, показывать
в админке, когда нужен новый аккаунт.

## Флаги (`.env`, по одному)

| Flag | Safe default | Meaning |
|---|---|---|
| `USERBOT_RPC_METRICS_ENABLED` | `true` | писать Redis buckets `stats:tg_rpc:*` |
| `USERBOT_GOVERNOR_ENFORCING` | `false` | proactive throttle меняет только recommended; FloodWait/circuit всегда effective |
| `USERBOT_ADAPTIVE_POLLING_ENABLED` | `false` | `false` = legacy tiers; `true` = due-loop, legacy catalog tiers off |

Safe budget defaults: `USERBOT_SAFE_DAILY_BUDGET=4000`, reserve `0.30`, slice `25`.

## Порядок rollout

1. **Не трогать prod без подтверждения владельца.**
2. `pg_dump` перед любым изменением образа/конфига (даже без миграций).
3. **Worker stop** перед image/config change; после Compose — `docker compose ps --all` и снова стоп worker при автозапуске.
4. Metrics shadow ≥24h (`RPC_METRICS=true`, `GOVERNOR_ENFORCING=false`, `ADAPTIVE=false`).
5. Сравнить projected vs actual RPC и SLO A/B.
6. Enable governor dry-run review в dashboard `/` (блок Userbot capacity).
7. Enforce на **одном** тестовом аккаунте (сначала вручную ограничить нагрузку маппингом / power через soft path) → наблюдение ≥2h, 0 FloodWait.
8. Второй аккаунт.
9. `USERBOT_ADAPTIVE_POLLING_ENABLED=true`.
10. После каждого старта worker: ≥5 минут `FloodWait|circuit|ERROR|CRITICAL`.
11. Rollback: выключить `USERBOT_GOVERNOR_ENFORCING` и/или `USERBOT_ADAPTIVE_POLLING_ENABLED`; **не удалять** `circuit:*` / `userbot:governor:*`.
12. Никогда не чистить Redis governor/circuit ради ускоренного «выздоровления».

## Telegram RPC governance

| Call site | Kind | Through limiter/governor? |
|---|---|---|
| `poller._resolve_entity` → `get_input_entity` | `resolve` | yes (`limiter.acquire`) |
| `poller._fetch_all_since` → `get_messages` | `get_history` | yes |
| `pool.check_health` → `get_me` | `health` | yes |
| `pool.start` → `get_me` (auth once) | auth bootstrap | **no** — one-shot at start, not polling |
| `discovery*` | discovery | isolated account / out of v1 governor namespace |
| `auth.py` | interactive auth | out of worker polling path |

`flood_sleep_threshold=0` в `UserbotAccount` — короткие FloodWait не глотаются Telethon.

## Rollback

```text
USERBOT_GOVERNOR_ENFORCING=false
USERBOT_ADAPTIVE_POLLING_ENABLED=false
# metrics можно оставить true
```

Restart **только bot/admin** flat `docker restart` если меняется только dashboard.
Любое изменение poller/rate_limiter/pool → worker restart только по команде владельца
после dump и с мониторингом FloodWait.

## Dashboard

`GET /api/stats/userbots` — read-only. UI без кнопок управления.
