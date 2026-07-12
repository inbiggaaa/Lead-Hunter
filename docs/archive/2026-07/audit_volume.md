# Аудит volume-mismatch migrations — 2026-07-04

## 0. Git
```
ahead=1, behind=0
```

## 1. Природа mismatch

### Владельцы
```
ХОСТ:      versions/ drwxr-xr-x 1000:1000 (leadhunter:leadhunter)
           файлы    -rw-rw-r-- 1000:1000
КОНТЕЙНЕР: versions/ drwxr-xr-x 0:0    (root:root)
           файлы    -rw-r--r-- 0:0    (root:root, кроме 4afd/b111=1000:1000)
```

### Процесс worker
```
uid=0(root) gid=0(root) groups=0(root)
```

### docker-compose mount
```yaml
volumes:
  - ./migrations:/app/migrations   # bind-mount, без user:/uid
```
`user:` не задан — контейнер работает под root.

### Root cause
`Dockerfile:14` делает `COPY . .` → образ УЖЕ содержит `/app/migrations/` (копию на момент сборки). При запуске bind-mount `./migrations:/app/migrations` ДОЛЖЕН перекрыть этот каталог, но overlay2 ведёт себя несогласованно:

- **device хост:** 8,1 (реальный диск)
- **device контейнер:** 0,45 (overlay2)

### Тест синка
```
HOST → контейнер (touch): НЕ ВИДЕН (cat: No such file or directory)
Контейнер → хост (0479):    НЕ ВИДЕН (ls: No such file or directory)
```

Bind-mount **сломан в обе стороны.** Контейнер видит снапшот каталога на момент старта, но живые изменения не синкаются.

## 2. Застрявший файл 0479

```python
revision: str = '0479653cd24b'
down_revision: Union[str, None] = 'c2a1d3b4e5f6'

def upgrade():
    op.add_column('catalog_channels', sa.Column('is_ignored', ...))      # ✓ нужное
    op.drop_constraint(op.f('uq_cities_country_slug'), 'cities', ...)    # ✗ лишнее
    op.drop_index(op.f('idx_sent_log_content_dedup'), 'sent_log')        # ✗ лишнее

def downgrade():
    op.create_index(...)       # обратное лишнему
    op.create_unique_constraint(...)
    op.drop_column(...)        # обратное нужному
```

## 3. Доступность хост-каталога

```
whoami: leadhunter
id:     uid=1000(leadhunter) gid=1000(leadhunter) groups=1000,27(sudo),100,988(docker)
versions/: drwxr-xr-x leadhunter:leadhunter
touch migrations/versions/.__wtest: OK ✓ (запись открыта)
```

## 4. РЕКОМЕНДАЦИЯ

**Лёгкий путь (предпочтительный):** писать миграцию прямо на хост.

У нас есть полный доступ на запись к `migrations/versions/`. Мы можем:
1. Создать исправленную версию миграции (только add_column, без drop_constraint/drop_index) руками на хосте
2. Удалить сломанный 0479 из контейнера (или просто перезаписать при следующем рестарте)
3. Применить миграцию через `docker compose exec worker alembic upgrade head` — upgrade использует хост-файлы (читает нормально, только запись не синкается)

Почему upgrade сработает: `alembic upgrade head` ЧИТАЕТ migration-файлы из `/app/migrations/versions/`. Поскольку файл будет лежать на хосте, а контейнер видит снапшот хоста на момент старта — нужно либо пересоздать контейнер (стоп worker), либо скопировать файл в контейнер через `docker compose cp`.

**План Б (если копирование в контейнер):** `docker compose cp migrations/versions/<file>.py worker:/app/migrations/versions/` — прямой трансфер, обходящий bind-mount.

**Compose-фикс (длинный путь, отложить):** добавить `user: "1000:1000"` в docker-compose worker + пересоздать контейнер. Это глобальный фикс, требует остановки worker.
