# ONBOARDING.md — Полный план запуска LeadHunter

Пошаговое руководство от чистого сервера до работающего бота. Выполнять строго по порядку.

---

## 0. Чек-лист перед стартом

- [ ] VPS сервер: Ubuntu 24.04, 2GB RAM, IP-адрес известен
- [ ] Доступ к серверу по SSH (root)
- [ ] Telegram-аккаунт для бота (может быть твой основной)
- [ ] Telegram-аккаунт для userbot (ОБЯЗАТЕЛЬНО отдельный номер!)

---

## 1. Сервер: базовая настройка

```bash
ssh root@<IP_СЕРВЕРА>

# 1.1 Обновление
apt update && apt upgrade -y

# 1.2 Swap 2GB (КРИТИЧНО для 2GB RAM!)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab
free -h  # проверить: Swap должен показывать 2GB

# 1.3 Часовой пояс
timedatectl set-timezone Europe/Moscow  # или свой

# 1.4 Инструменты
apt install -y git curl wget python3 python3-pip python3-venv ufw

# 1.5 Файрвол
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status

# 1.6 SSH-ключ (на рабочей машине, не на сервере!)
# На своём Mac:
ssh-copy-id root@<IP_СЕРВЕРА>
```

---

## 2. Docker

```bash
# 2.1 Установка
curl -fsSL https://get.docker.com | sh

# 2.2 Docker Compose
apt install -y docker-compose-plugin
docker compose version

# 2.3 Права
usermod -aG docker root
newgrp docker

# 2.4 Проверка
docker run hello-world
```

---

## 3. Регистрация бота в BotFather

```
1. Открой Telegram → найди @BotFather
2. Напиши: /newbot
3. Имя бота: LeadHunter
4. Username: LeadHunterBot (или свой)
5. Сохрани TOKEN:
   1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ↓
   Запиши в .env → BOT_TOKEN=...

6. Настройки бота (в @BotFather):
   /mybots → LeadHunterBot → Edit Bot
   → Edit Description: «Система мониторинга заявок в Telegram»
   → Edit About: «Нахожу клиентов в публичных чатах»
   → Edit Botpic: загрузи логотип
   → Bot Settings:
     • Allow Groups? → ENABLE
     • Group Privacy → DISABLED (чтобы видеть все сообщения)
```

---

## 4. Регистрация userbot (MTProto)

```
1. Зайди на https://my.telegram.org/apps
   (войди с ОТДЕЛЬНОГО номера, не основного!)

2. Create Application
   App title: LeadHunter Userbot
   Platform: Desktop
   Description: Channel monitoring

3. Сохрани:
   api_id: 12345678
   api_hash: abcdef1234567890abcdef1234567890
   ↓
   Запиши в .env:
   USERBOT_API_ID=12345678
   USERBOT_API_HASH=abcdef1234567890abcdef1234567890
   USERBOT_PHONE=+7XXXXXXXXXX
```

---

## 5. Платёжные системы (на будущее, Фаза 7)

### 5.1 Telegram Stars
```
Работает из коробки с BOT_TOKEN.
Ничего дополнительно настраивать не нужно.
```

### 5.2 CryptoBot
```
1. Найди @CryptoBot в Telegram
2. Напиши /start
3. → Crypto Pay → Create App
4. Название: LeadHunter
5. Сохрани API Token
   ↓
   Запиши в .env:
   CRYPTOBOT_API_TOKEN=...
   CRYPTOBOT_TESTNET=false  # в бою; true для тестов
```

### 5.3 DeepSeek API (LLM-валидация, опционально)
```
1. Зайди на https://platform.deepseek.com
2. Зарегистрируйся, пополни счёт ($5 хватит на месяцы)
3. API Keys → Create
   ↓
   Запиши в .env:
   DEEPSEEK_API_KEY=sk-...
   DEEPSEEK_MODEL=deepseek-chat
```

---

## 6. Клонирование проекта

```bash
cd /opt
git clone https://github.com/inbiggaaa/Lead-Hunter.git LeadHunter
cd LeadHunter
git log --oneline -3  # проверить что всё склонировалось
```

---

## 7. .env — заполнение секретов

```bash
cd /opt/LeadHunter
cp .env.example .env
nano .env
```

**Обязательные:**
```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
OWNER_TELEGRAM_ID=твой_telegram_id
USERBOT_API_ID=12345678
USERBOT_API_HASH=abcdef1234567890abcdef1234567890
USERBOT_PHONE=+7XXXXXXXXXX
POSTGRES_PASSWORD=<сгенерируй: openssl rand -hex 16>
ADMIN_PASSWORD=<надёжный пароль>
ADMIN_SECRET=<сгенерируй: openssl rand -hex 32>
```

**Опциональные (на будущее):**
```
CRYPTOBOT_API_TOKEN=...       # Фаза 7
DEEPSEEK_API_KEY=sk-...       # Фаза 4 (LLM-валидация)
SENTRY_DSN=...                # Фаза 8
```

**Как узнать свой telegram_id:**
```
1. Найди @userinfobot в Telegram
2. Напиши /start
3. Бот покажет твой ID → запиши в OWNER_TELEGRAM_ID
```

---

## 8. Установка pi (Claude Code)

```bash
# 8.1 Node.js (если нет)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs

# 8.2 Установка pi
npm install -g @earendil-works/pi-coding-agent

# 8.3 Первый запуск
cd /opt/LeadHunter
pi

# 8.4 Внутри pi настроить модель:
/model deepseek/deepseek-v4-pro
# ИЛИ
/model openrouter/deepseek/deepseek-chat

# 8.5 Выйти: Ctrl+C
```

---

## 9. Python-окружение

```bash
cd /opt/LeadHunter

# Виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Зависимости (когда появится requirements.txt — Фаза 1)
pip install --upgrade pip
```

---

## 10. VSCode Remote SSH

```
На рабочем Mac:

1. Установи расширение: "Remote - SSH"
   (ms-vscode-remote.ssh-remote-ssh)

2. Cmd+Shift+P → "Remote-SSH: Connect to Host"
3. Введи: root@<IP_СЕРВЕРА>
4. После подключения: File → Open Folder → /opt/LeadHunter

5. Терминал в VSCode теперь = SSH-терминал на сервере
6. В нём запускай pi
```

---

## 11. Первый запуск pi

```bash
cd /opt/LeadHunter
pi
```

pi автоматически прочитает CLAUDE.md и будет в контексте проекта.

**Первая команда:** «Начинаем Фазу 1 — скелет проекта. Создай структуру файлов, бот должен отвечать на /start.»

---

## 12. Рабочий процесс после каждой фазы

```bash
# 12.1 Проверка качества
/skill:phase-review
# → тесты → ревью → авто-фиксы → commit + tag

# 12.2 Или вручную:
pytest tests/ -v
git add -A
git commit -m "phase-1: скелет проекта, /start работает"
git tag phase-1-done
git push
git push --tags
```

---

## 13. Проверка готовности

```bash
cd /opt/LeadHunter

# Файлы проекта
ls -la
# CLAUDE.md, DECISIONS.md, ROADMAP.md, DISCOVERY.md, USERFLOW.md,
# SEED.md, CODING_STYLE.md, TESTING.md, RECOVERY.md, SETUP.md,
# segment_seed.md, .env, .env.example, .gitignore

# Git
git status   # clean
git log --oneline -3  # видно историю

# Docker
docker --version
docker compose version

# Swap
free -h | grep Swap  # 2.0G

# Файрвол
ufw status  # 22, 80, 443 allowed

# VSCode
# Открыть /opt/LeadHunter через Remote SSH → работает
```

---

## Чек-лист готовности к Фазе 1

- [ ] Сервер настроен (swap, файрвол, часовой пояс)
- [ ] Docker работает
- [ ] Бот зарегистрирован в @BotFather, токен в .env
- [ ] Userbot зарегистрирован на my.telegram.org, api_id/hash в .env
- [ ] Проект склонирован из GitHub в /opt/LeadHunter
- [ ] .env заполнен всеми секретами
- [ ] .env в .gitignore (проверить: git status не показывает .env)
- [ ] pi установлен и запускается
- [ ] VSCode подключается по SSH
- [ ] Git настроен (user.name, user.email)
- [ ] Платёжные API-ключи получены (CryptoBot, DeepSeek — опционально)
