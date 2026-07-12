# Аудит рассинхрона Alembic — 2026-07-04

## 0. Git
```
ahead=1, behind=0 ✓
```

## 1. ФАКТ схемы — content_hash

**ЕСТЬ.** И колонка, и индекс присутствуют в sent_log:

```
column_name  | data_type        | is_nullable
content_hash | character varying | YES

indexname: idx_sent_log_content_dedup (user_id, content_hash, sent_at)
```

Миграция `c2a1d3b4e5f6` ФАКТИЧЕСКИ ПРИМЕНЕНА.

## 2. УЧЁТ Alembic

```
alembic_version table: 4afd135dc3f1, b11187f388a9 (2 rows)
alembic current:       b11187f388a9
alembic history head:  c2a1d3b4e5f6
```

**Расхождение:** БД = b11187f388a9, head на диске = c2a1d3b4e5f6.

## 3. Содержимое спорной ревизии

`c2a1d3b4e5f6` (parent: `b11187f388a9`, chain: последовательная):
```python
def upgrade():
    op.add_column("sent_log", sa.Column("content_hash", sa.String(64), nullable=True))
    op.create_index("idx_sent_log_content_dedup", "sent_log", ["user_id", "content_hash", "sent_at"])

def downgrade():
    op.drop_index("idx_sent_log_content_dedup", table_name="sent_log")
    op.drop_column("sent_log", "content_hash")
```

**НЕ идемпотентна** — IF NOT EXISTS отсутствует. Повторный `alembic upgrade head` упадёт с duplicate column error.

## 4. Цепочка ревизий (диск vs учёт)

| Диск | down_revision | В БД (alembic_version) |
|---|---|---|
| ca16bab1a0cc (initial) | `<base>` | ✅ |
| da0a81014466 | ca16bab1a0cc | ✅ (через parent) |
| 4afd135dc3f1 | da0a81014466 | ✅ |
| b11187f388a9 | 4afd135dc3f1 | ✅ |
| c2a1d3b4e5f6 | b11187f388a9 | ❌ ОТСУТСТВУЕТ |

Цепочка **последовательна** — обрывов/ветвлений нет. `c2a1d3b4e5f6` child of `b11187f388a9`.

## 5. ВЫВОД: Состояние A

**Учёт отстал — нужен stamp, НЕ upgrade.**

Обоснование:
- Колонка + индекс существуют в БД → миграция применена
- alembic_version не содержит c2a1d3b4e5f6 → учёт отстал
- upgrade() не идемпотентна → `alembic upgrade head` упадёт
- Alembic history показывает корректную цепочку без обрывов

**Исправление (НЕ делать сейчас, только план):**
```bash
docker compose exec worker alembic stamp c2a1d3b4e5f6
```
Это запишет `c2a1d3b4e5f6` в `alembic_version` без выполнения upgrade(). После этого `alembic current` = `c2a1d3b4e5f6` = head, и можно создавать новую ревизию для is_ignored.

Почему рассинхрон произошёл: вероятно, миграция была накатана через `docker compose run` (тестовый контейнер), а не через `docker compose exec` (основной worker). Повторный `run` создаёт новый контейнер → новая сессия Alembic → stamp не переносится в основной контейнер.

**Следующий шаг (после решения):** `alembic stamp c2a1d3b4e5f6` → `alembic revision --autogenerate -m "add is_ignored"` → `alembic upgrade head`.
