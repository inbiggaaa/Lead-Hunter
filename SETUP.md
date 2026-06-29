# Фаза 0 — Подготовка сервера и инструментов

**Сервер:** Ubuntu 24.04, 2GB RAM, 1 Core
**Репозиторий:** https://github.com/inbiggaaa/Lead-Hunter

---

## Шаг 1: Базовая настройка сервера

```bash
# Подключаемся по SSH
ssh root@<IP_СЕРВЕРА>

# Обновляем систему
apt update && apt upgrade -y

# Swap 2GB (критично для 2GB RAM!)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab

# Базовые инструменты
apt install -y git curl wget python3 python3-pip python3-venv ufw

# Файрвол — только SSH (и 80/443 на будущее)
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

---

## Шаг 2: Docker

```bash
# Установка Docker
curl -fsSL https://get.docker.com | sh

# Docker без sudo
usermod -aG docker $USER
newgrp docker  # или перелогинься

# Проверка
docker --version
docker run hello-world
```

---

## Шаг 3: Клонирование проекта

```bash
# Создаём рабочую директорию
mkdir -p /opt/LeadHunter
cd /opt/LeadHunter

# Клонируем репозиторий
git clone https://github.com/inbiggaaa/Lead-Hunter.git .

# Настраиваем git
git config user.name "Dima Braim"
git config user.email "твой@email.com"

# Проверяем
git log --oneline -3
ls -la
```

---

## Шаг 4: .env

```bash
# Копируем шаблон
cp .env.example .env

# Редактируем — заполняем ВСЕ токены
nano .env
# BOT_TOKEN=...
# USERBOT_API_ID=...
# USERBOT_API_HASH=...
# POSTGRES_PASSWORD=...
# ADMIN_SECRET=$(openssl rand -hex 32)
# и т.д.
```

---

## Шаг 5: Установка pi (Claude Code)

```bash
# Устанавливаем pi глобально
npm install -g @earendil-works/pi-coding-agent

# Запускаем первый раз — настроит конфиг
pi

# В интерактивном режиме:
# /model — проверить модель
# /login — подключить API-ключи
```

### Настройка модели

```bash
# Внутри pi:
/model openrouter/deepseek/deepseek-chat
# или
/model deepseek/deepseek-v4-pro
```

### Настройка пакетов

Убедись что в `~/.pi/agent/settings.json` есть пакеты:
```json
{
  "packages": [
    "npm:@juicesharp/rpiv-pi",
    "git:github.com/mattpocock/skills",
    "npm:@tintinweb/pi-subagents"
  ]
}
```

---

## Шаг 6: VSCode Remote SSH

### На рабочей машине (macOS)

```bash
# 1. Установи расширение: Remote - SSH (ms-vscode-remote.ssh-remote)
# 2. Cmd+Shift+P → Remote-SSH: Connect to Host
# 3. Введи: root@<IP_СЕРВЕРА>
# 4. После подключения: File → Open Folder → /opt/LeadHunter
```

### SSH-ключ (чтобы не вводить пароль)

```bash
# На рабочей машине:
ssh-copy-id root@<IP_СЕРВЕРА>

# Проверка:
ssh root@<IP_СЕРВЕРА>  # должен пускать без пароля
```

---

## Шаг 7: Рабочий процесс

```bash
# 1. Открываешь VSCode → /opt/LeadHunter
# 2. В терминале VSCode: pi (запускает Claude Code)
# 3. Claude Code видит CLAUDE.md, работает с контекстом проекта
# 4. После каждого изменения:
git add -A
git commit -m "phase-0: описание"
git push

# 5. После завершения фазы:
git tag phase-0-done
git push --tags
```

---

## Шаг 8: Проверка готовности

```bash
# Проверяем что всё на месте:
cd /opt/LeadHunter
ls -la

# Должны быть:
# CLAUDE.md, DECISIONS.md, ROADMAP.md, DISCOVERY.md
# USERFLOW.md, SEED.md, CODING_STYLE.md, TESTING.md
# RECOVERY.md, segment_seed.md
# .env, .env.example, .gitignore

# Git status
git status
# On branch main, nothing to commit

# Docker
docker --version  # должно показать версию

# Python
python3 --version  # 3.11+

# pi
pi --version  # или pi -c (продолжить последнюю сессию)
```

---

## После Фазы 0

- [ ] SSH работает по ключу
- [ ] Docker установлен
- [ ] Проект склонирован из GitHub
- [ ] `.env` заполнен токенами
- [ ] VSCode подключается по SSH
- [ ] pi запускается и видит CLAUDE.md
- [ ] Swap 2GB работает
- [ ] Файрвол настроен

**Следующая: Фаза 1 — скелет проекта, бот отвечает на /start.**
