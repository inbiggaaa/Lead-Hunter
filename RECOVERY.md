# RECOVERY.md — План восстановления LeadHunter

Этот файл читать при ЛЮБОЙ поломке. Спокойно, по шагам.

---

## 0. Золотое правило

**Не паниковать. Не делать `docker compose down -v` без понимания проблемы.**

`-v` удаляет все Docker-вольюмы включая БД. Только если точно знаешь что делаешь.

---

## 1. Диагностика: что сломалось?

```bash
# Шаг 1: все контейнеры живы?
docker compose ps

# Шаг 2: логи последних 50 строк по всем сервисам
docker compose logs --tail=50

# Шаг 3: потребление памяти (сервер 2GB!)
docker stats --no-stream

# Шаг 4: место на диске
df -h
```

---

## 2. Распространённые проблемы

### Бот не отвечает на /start

```bash
# Проверить bot
docker compose logs bot --tail=20

# Частая причина: BOT_TOKEN невалидный или протух
# Проверить .env:
grep BOT_TOKEN .env

# Перезапустить
docker compose up -d bot
```

### Уведомления не приходят

```bash
# 1. Userbot жив?
docker compose logs worker --tail=30 | grep -i "error\|disconnect\|flood"

# 2. Heartbeat в порядке?
docker compose exec redis redis-cli GET heartbeat:userbot:1
# Если (nil) — userbot не пишет heartbeat. Проверить логи.

# 3. Очередь растёт?
docker compose exec redis redis-cli LLEN queue:notifications
# Если > 100 и растёт — sender не справляется. Проверить логи sender.

# 4. Dead-letter?
docker compose exec redis redis-cli LLEN dlq:notifications
# Если > 0 — есть неотправленные уведомления. Разобрать вручную или дождаться worker.
```

### PostgreSQL не стартует

```bash
docker compose logs db --tail=30

# Частая причина: диск полон
df -h /var/lib/docker

# Частая причина: corrupt WAL
# Решение: восстановить из бэкапа (см. раздел 3)
```

### Контейнер уходит в OOM-kill (Out of Memory)

```bash
docker compose logs --tail=50 | grep -i "killed\|oom\|out of memory"

# Сервер 2GB. Если OOM — увеличить swap:
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Или пересмотреть memory limits в docker-compose.yml
```

### Redis перезапустился — уведомления потеряны

```bash
# Проверить, был ли рестарт Redis
docker compose logs redis --tail=20 | grep -i "ready\|restart"

# Очередь пуста — это нормально после рестарта (LPUSH/BRPOP — in-memory)
docker compose exec redis redis-cli LLEN queue:notifications

# Уведомления за время простоя потеряны безвозвратно.
# При росте нагрузки рассмотреть Redis Streams (XADD/XREADGROUP/XACK).
```

### Userbot забанен / FloodWait

```bash
# FloodWaitError — ждём ровно error.seconds, больше ничего не делаем.
# Если бан — проверить аккаунт вручную:
# 1. Залогиниться в Telegram с этого номера
# 2. Проверить — может, спам-блок?
# 3. Если аккаунт не recoverable — сбросить сессию:
rm sessions/userbot.session
docker compose run --rm -it worker python -m app.userbot.auth
```

---

## 3. Восстановление БД из бэкапа

```bash
# 1. Найти последний бэкап
ls -lt /backups/ | head -5

# 2. Остановить все контейнеры кроме db
docker compose stop bot worker admin

# 3. Восстановить
BACKUP_FILE=$(ls -t /backups/leadhunter_*.sql | head -1)
docker compose exec -T db psql -U leadhunter -d leadhunter < "$BACKUP_FILE"

# 4. Поднять всё
docker compose up -d

# 5. Проверить
docker compose logs --tail=20
```

---

## 4. Полный перезапуск сервера

```bash
# После перезагрузки сервера (reboot):
cd /opt/LeadHunter  # или твой путь
docker compose up -d
docker compose logs --tail=20

# Убедиться что все 5 контейнеров Running:
docker compose ps
```

---

## 5. Полная переустановка (с нуля)

```bash
# ТОЛЬКО если сервер новый или всё сломано невосстановимо.

# 1. Клонировать репозиторий
git clone <repo_url> /opt/LeadHunter
cd /opt/LeadHunter

# 2. Скопировать .env с секретами (хранить отдельно!)
# Если .env утерян — восстановить из .env.example и задать все значения

# 3. Скопировать сессию userbot (если есть бэкап)
mkdir -p sessions
cp /backup/path/userbot.session sessions/

# 4. Запустить
docker compose up -d --build

# 5. Применить миграции
docker compose exec bot alembic upgrade head

# 6. Засеять каталог
docker compose exec bot python seed/seed_catalog.py

# 7. Авторизовать userbot (если сессии нет)
docker compose run --rm -it worker python -m app.userbot.auth

# 8. Восстановить БД из бэкапа (см. раздел 3)
```

---

## 6. Контакты и внешние сервисы

| Сервис | Что делать если не работает |
|---|---|
| Telegram Bot API | Проверить status.telegram.org |
| MTProto (userbot) | Проверить my.telegram.org — API_ID валиден? |
| CryptoBot | Проверить testnet/mainnet URL в .env |
| PostgreSQL | Локальный — см. раздел 2 |
| Redis | Локальный — см. раздел 2 |

---

## 7. Превентивные меры

- [ ] Бэкап БД раз в сутки (cron)
- [ ] `docker compose logs --tail=20` — раз в день, убедиться что нет ошибок
- [ ] `df -h` — раз в неделю, убедиться что диск не забит
- [ ] Heartbeat-алерт в Telegram — если userbot упал, ты узнаешь
- [ ] `.env` и `sessions/userbot.session` — забэкаплены отдельно от сервера
